"""Reproducible chronological benchmark. Run from the repository root."""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, brier_score_loss, confusion_matrix,
                             f1_score, precision_recall_curve, precision_score, recall_score,
                             roc_auc_score, silhouette_score)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml.config import (ARTIFACTS, BASE, DISCLAIMER, EMBARGO_DAYS, FEATURES, HOLDOUT_STATIONS,
                       RAW, SEED, TARGET, TIERS)
from ml.data import audit, build_features, representative_subset, screen_labels, stations
from ml.download import download


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def metrics(y, probability, threshold):
    y = np.asarray(y, dtype=int)
    probability = np.asarray(probability, dtype=float)
    if not len(y):
        return {"rows": 0, "reason": "No evaluation rows"}
    predicted = probability >= threshold
    two_classes = len(np.unique(y)) == 2
    return {
        "rows": len(y), "positives": int(y.sum()), "prevalence": float(y.mean()),
        "precision": float(precision_score(y, predicted, zero_division=0)),
        "recall": float(recall_score(y, predicted, zero_division=0)),
        "f1": float(f1_score(y, predicted, zero_division=0)),
        "pr_auc_average_precision": float(average_precision_score(y, probability)) if two_classes else None,
        "roc_auc": float(roc_auc_score(y, probability)) if two_classes else None,
        "brier": float(brier_score_loss(y, probability)),
        "confusion_matrix_tn_fp_fn_tp": confusion_matrix(y, predicted, labels=[0, 1]).ravel().astype(int).tolist(),
        "auc_note": None if two_classes else "AUC undefined: only one class present",
    }


def choose_threshold(y, probability):
    precision, recall, thresholds = precision_recall_curve(y, probability)
    scores = 2 * precision[:-1] * recall[:-1] / np.maximum(precision[:-1] + recall[:-1], 1e-12)
    return float(thresholds[int(np.argmax(scores))])


def candidates(smoke=False):
    # Small predeclared search; no test-set driven hyperparameter changes.
    iterations = 15 if smoke else 250
    for weight in (None, "balanced"):
        yield "logistic_regression", {"class_weight": weight}, LogisticRegression(C=1.0, class_weight=weight, max_iter=2000, random_state=SEED)
    for depth in (6, 12):
        yield "random_forest", {"max_depth": depth}, RandomForestClassifier(n_estimators=20 if smoke else 180, max_depth=depth, min_samples_leaf=8, n_jobs=2, random_state=SEED)
    from lightgbm import LGBMClassifier
    from catboost import CatBoostClassifier
    for leaves in (7, 15):
        yield "lightgbm", {"num_leaves": leaves}, LGBMClassifier(n_estimators=iterations, num_leaves=leaves, learning_rate=0.04, verbosity=-1, n_jobs=2, random_state=SEED, deterministic=True, force_col_wise=True)
    for depth in (4, 6):
        yield "catboost", {"depth": depth}, CatBoostClassifier(iterations=iterations, depth=depth, learning_rate=0.05, random_seed=SEED, thread_count=2, verbose=False, allow_writing_files=False)


def pipeline(estimator):
    return Pipeline([("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
                     ("scale", StandardScaler()), ("classifier", estimator)])


def fit_candidates(train, validation, smoke=False):
    if train[TARGET].nunique() != 2 or validation[TARGET].nunique() != 2:
        raise ValueError("Both train and validation need both classes")
    selected, searches = {}, []
    for name, parameters, estimator in candidates(smoke):
        started = time.monotonic()
        fitted = pipeline(estimator).fit(train[FEATURES], train[TARGET].astype(int))
        probabilities = fitted.predict_proba(validation[FEATURES])[:, 1]
        score = float(average_precision_score(validation[TARGET], probabilities))
        threshold = choose_threshold(validation[TARGET], probabilities)
        searches.append(dict(model=name, parameters=parameters, validation_pr_auc=score,
                             seconds=time.monotonic() - started, threshold=threshold))
        print(f"{name} {parameters}: validation AP={score:.4f}", flush=True)
        if name not in selected or score > selected[name]["score"]:
            selected[name] = dict(pipeline=fitted, score=score, threshold=threshold, parameters=parameters)
    return selected, searches


def cluster(subset, out):
    # Hydrometeorology only: excludes label, regime, date, station ID and terrain.
    columns = BASE + ["rainfall_local_mm_sum7d", "rainfall_upstream_mm_sum14d", "river_discharge_m3s_mean7d"]
    train = subset[subset.partition.eq("train")]
    preparation = Pipeline([("imputer", SimpleImputer()), ("scale", StandardScaler())])
    values = preparation.fit_transform(train[columns])
    comparisons, best = [], None
    for count in (2, 3, 4, 5):
        model = KMeans(n_clusters=count, n_init=10, random_state=SEED).fit(values)
        score = float(silhouette_score(values, model.labels_, sample_size=min(2000, len(train)), random_state=SEED))
        comparisons.append(dict(k=count, train_silhouette=score, inertia=float(model.inertia_)))
        if best is None or score > best[0]:
            best = (score, model)
    model = best[1]
    fitted = Pipeline([("preprocessing", preparation), ("kmeans", model)])
    assigned = subset[["date", "station_id", "partition"]].copy()
    assigned["cluster"] = fitted.predict(subset[columns])
    assigned.to_csv(out / "clusters.csv", index=False)
    train_labels = model.labels_
    profiles = train[columns].groupby(train_labels).mean()
    profiles.to_csv(out / "cluster_profiles.csv", index_label="cluster")
    counts = assigned.groupby(["partition", "cluster"]).size().unstack(fill_value=0)
    counts.to_csv(out / "cluster_partition_counts.csv")
    joblib.dump({"pipeline": fitted, "features": columns}, out / "clustering.joblib")
    descriptions = {}
    for i, centroid in enumerate(model.cluster_centers_):
        dominant = np.argsort(np.abs(centroid))[-3:][::-1]
        descriptions[str(i)] = [f"{columns[j]}: {'above' if centroid[j] > 0 else 'below'} training mean ({centroid[j]:.2f} SD)" for j in dominant]
    write_json(out / "clustering.json", {"comparison": comparisons, "selected_k": model.n_clusters,
               "features": columns, "weather_patterns": descriptions,
               "interpretation": "Unsupervised weather/hydrology groups. Cluster numbers are arbitrary and are not verified flood-risk labels."})
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].plot([c["k"] for c in comparisons], [c["train_silhouette"] for c in comparisons], marker="o")
    axes[0].set(xlabel="Number of clusters", ylabel="Training silhouette")
    artist = axes[1].imshow(model.cluster_centers_, aspect="auto", cmap="coolwarm", vmin=-3, vmax=3)
    axes[1].set_xticks(range(len(columns)), columns, rotation=75, ha="right", fontsize=7)
    axes[1].set(ylabel="Arbitrary cluster ID", title="Scaled weather centroids (training only)")
    fig.colorbar(artist, ax=axes[1], label="Standard deviations")
    fig.tight_layout(); fig.savefig(out / "clustering.png", dpi=150); plt.close(fig)


def train(out=ARTIFACTS, rows=30000, smoke=False):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if (out / "model_metadata.json").exists():
        raise ValueError("Run already finalized. Use a new --out directory; do not tune against this test.")
    provenance = download(offline=True)
    raw = pd.read_parquet(RAW / "all_stations.parquet")
    audit(raw, out)
    registry = stations()
    full = build_features(raw, registry)
    subset = representative_subset(full, rows)
    subset.to_parquet(out / "subset.parquet", index=False)
    subset[["station_id", "date", "selection_hash", "partition"]].to_csv(out / "subset_manifest.csv", index=False)
    summary = subset.groupby("partition")[TARGET].agg(["count", "sum", "mean"])
    summary.to_csv(out / "partition_summary.csv")
    # Report sampling changes after selection, never use labels to change selection.
    eligible = full.loc[screen_labels(full)].dropna(subset=FEATURES)
    sampling = {"method": "Lowest SHA256(station_id:date:314), target-independent uniform sample, before partition assignment",
                "eligible_rows": len(eligible), "subset_rows": len(subset), "seed": SEED,
                "screened_prevalence": float(eligible[TARGET].mean()), "subset_prevalence": float(subset[TARGET].mean()),
                "holdout_stations": HOLDOUT_STATIONS, "embargo_days": EMBARGO_DAYS,
                "excluded": "Holdout-station dates before test start and 3 days before each time boundary remain excluded.",
                "subset_sha256": hashlib.sha256((out / "subset.parquet").read_bytes()).hexdigest()}
    write_json(out / "sampling.json", sampling)
    parts = {p: subset[subset.partition.eq(p)] for p in ("train", "validation", "test", "holdout_station")}
    selected, searches = fit_candidates(parts["train"], parts["validation"], smoke)
    winner = max(selected, key=lambda name: selected[name]["score"])
    evaluation = {"selected_by_validation_ap": winner, "candidates": {}, "search": searches,
                  "test_policy": "One pass after model and threshold selection; no refit or resampling; single frozen run.",
                  "uncertainty": "Daily events and nearby model grids are correlated; no independent-event confidence interval claimed."}
    predictions = {}
    for name, fitted in selected.items():
        results = {"parameters": fitted["parameters"], "threshold": fitted["threshold"]}
        for split, data in parts.items():
            probability = fitted["pipeline"].predict_proba(data[FEATURES])[:, 1]
            results[split] = metrics(data[TARGET], probability, fitted["threshold"])
            if name == winner:
                predictions[split] = probability
                per_station = {sid: metrics(group[TARGET], probability[data.station_id.eq(sid).to_numpy()], fitted["threshold"])
                               for sid, group in data.groupby("station_id")}
                write_json(out / f"metrics_per_station_{split}.json", per_station)
        evaluation["candidates"][name] = results
    write_json(out / "evaluation.json", evaluation)
    best = selected[winner]
    joblib.dump(best["pipeline"], out / "classifier.joblib")
    write_json(out / "thresholds.json", {"binary_threshold": best["threshold"], "selected_on": "validation maximum F1",
               "presentation_tiers": TIERS, "presentation_status": "Provisional; not calibrated safety thresholds"})
    schema = {"features": FEATURES, "required": FEATURES, "additional_features": False,
              "history": "Daily current values, lags 1/2/3/5 and trailing inclusive 7/14-day sums or means, constructed within station.",
              "availability": "Historical replay only after feature day closes; reanalysis release latency unknown. No future data in windows.",
              "location": "Approximate source station latitude/longitude; ID and name are audit keys, not model inputs.",
              "units": {"rainfall": "mm/day; trailing sums in mm", "discharge": "m3/s", "soil_moisture": "source volumetric fraction", "terrain": "metres", "coordinates": "degrees"}}
    write_json(out / "feature_schema.json", schema)
    write_json(out / "stations.json", registry)
    write_json(out / "provenance.json", provenance)
    # Display examples are chosen ONLY after all evaluation is frozen. Extremes
    # illustrate software behavior, not representative accuracy or causal risk.
    data = parts["test"].copy()
    data["probability"] = predictions["test"]
    examples = []
    for kind, index in (("normal", data.probability.idxmin()), ("high_risk", data.probability.idxmax())):
        row = data.loc[index]
        examples.append({"id": kind, "selection": "Held-out test minimum/maximum model probability; cherry-picked demonstration, not performance evidence",
                         "station": registry[row.station_id], "feature_date": row.date.strftime("%Y-%m-%d"),
                         "as_of": row.date.strftime("%Y-%m-%dT23:59:59Z"), "country": "Bangladesh",
                         "mode": "historical_replay", "features": {c: float(row[c]) for c in FEATURES},
                         "observed_proxy_label": int(row[TARGET]), "expected_probability": float(row.probability)})
    write_json(out / "replay_examples.json", examples)
    score_table = pd.DataFrame({name: candidate["test"] for name, candidate in evaluation["candidates"].items()}).T
    score_table.to_csv(out / "model_comparison.csv")
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for name, candidate in selected.items():
        prob = candidate["pipeline"].predict_proba(parts["test"][FEATURES])[:, 1]
        precision, recall, _ = precision_recall_curve(parts["test"][TARGET], prob)
        axes[0].plot(recall, precision, label=name)
    axes[0].axhline(parts["test"][TARGET].mean(), color="gray", linestyle="--", label="Prevalence")
    axes[0].set(xlabel="Recall", ylabel="Precision", title="Untouched chronological test"); axes[0].legend(fontsize=7)
    matrix = np.array(evaluation["candidates"][winner]["test"]["confusion_matrix_tn_fp_fn_tp"]).reshape(2, 2)
    axes[1].imshow(matrix, cmap="Blues")
    for (i, j), value in np.ndenumerate(matrix): axes[1].text(j, i, str(value), ha="center", va="center")
    axes[1].set(xlabel="Predicted class", ylabel="Source proxy label", title=winner)
    # Equal-width reliability bins, descriptive only; no post-test calibration.
    y = parts["test"][TARGET].to_numpy(); p = predictions["test"]
    for lo in np.arange(0, 1, 0.1):
        mask = (p >= lo) & (p < lo + 0.1 + (1e-10 if lo > 0.89 else 0))
        if mask.any(): axes[2].scatter(p[mask].mean(), y[mask].mean(), s=15 + 3*np.sqrt(mask.sum()), color="steelblue")
    axes[2].plot([0, 1], [0, 1], "--", color="gray")
    axes[2].set(xlabel="Mean predicted probability", ylabel="Observed proxy fraction", title="Reliability (uncalibrated)")
    fig.tight_layout(); fig.savefig(out / "performance.png", dpi=160); plt.close(fig)
    cluster(subset, out)
    versions = {p: importlib.metadata.version(p) for p in ["pandas", "numpy", "scikit-learn", "joblib", "pyarrow", "lightgbm", "catboost", "matplotlib"]}
    metadata = {"model_version": "bd-research-" + sampling["subset_sha256"][:12] + ("-smoke" if smoke else "-v1"),
                "selected_model": winner, "trained_at": datetime.now(timezone.utc).isoformat(),
                "research_mode": True, "mode": "historical_replay", "horizon_hours": 24,
                "target": TARGET, "negative_label": "Source-observed proxy negative, not independently verified physical non-flood",
                "disclaimer": DISCLAIMER, "versions": versions, "python": platform.python_version(),
                "classifier_sha256": hashlib.sha256((out / "classifier.joblib").read_bytes()).hexdigest(),
                "source": provenance["repository"], "source_commit": provenance["commit"],
                "tabfm": {"status": "not_benchmarked", "reason": "Optional benchmark deferred; no separate compatible environment or licensed weights installed. Baselines complete independently.",
                          "source": "https://github.com/google-research/tabfm", "default_context_rows": 100,
                          "licensing": "Apache-2.0 code; default weights have separate non-commercial, non-production license. Review terms before download."},
                "smoke_only": smoke}
    # Metadata is the final completion marker; inference rejects incomplete runs.
    write_json(out / "model_metadata.json", metadata)
    print(json.dumps({"winner": winner, "test": evaluation["candidates"][winner]["test"], "out": str(out)}, indent=2))
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=30000)
    parser.add_argument("--out", type=Path, default=ARTIFACTS)
    parser.add_argument("--smoke", action="store_true", help="Short estimators only; not final reported research results")
    arguments = parser.parse_args()
    train(arguments.out, arguments.rows, arguments.smoke)
