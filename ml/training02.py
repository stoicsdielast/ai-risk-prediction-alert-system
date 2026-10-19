"""Staged refinement of training-01. No fitting stage reads final evaluation data."""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import shutil
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
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve, silhouette_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from ml.config import BASE, DISCLAIMER, FEATURES, HOLDOUT_STATIONS, RAW, SEED, TARGET, TIERS
from ml.data import audit, screen_labels, split_rows, stations
from ml.refinement import (EXTRA_FEATURES, FEATURE_SETS, VALIDATION_WINDOWS, assert_disjoint, calibrated,
                           development_stages, directory_hashes, extended_features, recall_budget_threshold,
                           reliability, score, selection_choice, sha256, threshold_table)
from ml.train import pipeline, write_json

DEFAULT_BASELINE = Path("ml/runs/training-01")
DEFAULT_OUT = Path("ml/runs/training-02")
DEVELOPMENT = ["train", *VALIDATION_WINDOWS]


def read(path):
    return json.loads(Path(path).read_text())


def protect_paths(out, baseline):
    out, baseline = Path(out).resolve(), Path(baseline).resolve()
    if out == baseline or out.is_relative_to(baseline) or baseline.is_relative_to(out):
        raise ValueError("Output must be separate from training-01, never its parent or child")


def verify_baseline(out):
    plan = read(out / "plan.json")
    baseline = Path(plan["baseline_directory"])
    if directory_hashes(baseline) != plan["baseline_file_hashes"]:
        raise ValueError("Baseline contents changed since the audit; refusing to continue")
    return baseline, plan


def load_development(out):
    verify_baseline(out)
    if sha256(out / "development.parquet") != read(out / "audit_complete.json")["development_sha256"]:
        raise ValueError("Development data changed after audit")
    data = pd.read_parquet(out / "development.parquet")
    parts = {part: data.loc[data.stage.eq(part)].copy() for part in DEVELOPMENT}
    assert_disjoint(parts)
    if not data.stage.isin(DEVELOPMENT).all():
        raise ValueError("Non-development rows found in fitting input")
    return data, parts


def specifications():
    specs = []
    for feature_set in FEATURE_SETS:
        for balanced in (False, True):
            for c in (.1, 1., 10.):
                specs.append(dict(family="logistic", feature_set=feature_set, balanced=balanced, parameters={"C": c}))
            for leaves, minimum, regularization in ((7, 30, 1.), (15, 60, 5.)):
                specs.append(dict(family="lightgbm", feature_set=feature_set, balanced=balanced,
                                  parameters={"num_leaves": leaves, "min_child_samples": minimum, "reg_lambda": regularization}))
            for depth, regularization in ((4, 5.), (6, 10.)):
                specs.append(dict(family="catboost", feature_set=feature_set, balanced=balanced,
                                  parameters={"depth": depth, "l2_leaf_reg": regularization}))
    return specs


def estimator(spec):
    parameters = spec["parameters"]
    if spec["family"] == "logistic":
        return LogisticRegression(**parameters, class_weight="balanced" if spec["balanced"] else None,
                                  max_iter=2000, random_state=SEED)
    if spec["family"] == "lightgbm":
        from lightgbm import LGBMClassifier
        return LGBMClassifier(**parameters, n_estimators=350, learning_rate=.035, verbosity=-1, n_jobs=2,
                              class_weight="balanced" if spec["balanced"] else None,
                              random_state=SEED, deterministic=True, force_col_wise=True)
    from catboost import CatBoostClassifier
    return CatBoostClassifier(**parameters, iterations=350, learning_rate=.04,
                             auto_class_weights="Balanced" if spec["balanced"] else None,
                             random_seed=SEED, thread_count=2, verbose=False, allow_writing_files=False)


def audit_stage(out, baseline):
    protect_paths(out, baseline)
    if out.exists():
        raise ValueError(f"Output already exists: {out}; audit never overwrites a run")
    metadata = read(baseline / "model_metadata.json")
    if sha256(baseline / "classifier.joblib") != metadata["classifier_sha256"]:
        raise ValueError("Baseline classifier integrity mismatch")
    provenance = read(baseline / "provenance.json")
    for local, facts in provenance["files"].items():
        if sha256(RAW / local) != facts["sha256"]:
            raise ValueError(f"Source integrity mismatch: {local}")
    old = pd.read_parquet(baseline / "subset.parquet")
    if not old.partition.equals(split_rows(old)):
        raise ValueError("Saved original partitions differ from the declared time/station split")
    if old.duplicated(["station_id", "date"]).any():
        raise ValueError("Duplicate baseline station/date keys")
    out.mkdir(parents=True)
    plan = {
        "study": "training-02", "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline_directory": str(baseline.resolve()), "baseline_file_hashes": directory_hashes(baseline),
        "source_sha256": provenance["files"]["all_stations.parquet"]["sha256"],
        "seed": SEED, "feature_sets": FEATURE_SETS, "search": specifications(),
        "windows_exclusive_end": VALIDATION_WINDOWS, "embargo_days": 3,
        "tuning_rule": "Maximum tuning average precision within each family/feature-set/weight group",
        "calibration_rule": "Frozen base estimator; sigmoid/isotonic fitted only on 2022 H2",
        "selection_rule": "Minimum 2023 H1 Brier among candidates retaining >=95% of original baseline AP on the same block",
        "threshold_rule": "Maximum 2023 H2 recall subject to FP/TP no worse than original baseline on the same block; ties use fewer FP, then higher threshold",
        "false_alert_budget_authorization": "User selected baseline false-alerts-per-detection budget",
        "test_policy": "Only the frozen original and selected pipeline are scored at final evaluation, with thresholds locked first. Never fit on final-test or held-out-station records.",
        "reuse_caveat": "The original temporal/station test metrics were previously inspected; this is a frozen retrospective comparison, not a newly blind prospective test.",
        "disclaimer": DISCLAIMER,
    }
    write_json(out / "plan.json", plan)
    raw = pd.read_parquet(RAW / "all_stations.parquet")
    report = audit(raw, out / "audit")
    enriched = extended_features(raw, stations())
    subset = old[["date", "station_id", "partition", "selection_hash"]].merge(enriched, on=["date", "station_id"], how="left", validate="one_to_one")
    if len(subset) != len(old) or not screen_labels(subset).all():
        raise ValueError("Not all baseline keys retain source-qualified labels")
    for c in [TARGET, *FEATURES]:
        if not np.allclose(subset[c].to_numpy(), old[c].to_numpy(), equal_nan=True):
            raise ValueError(f"Reconstructed baseline feature/label changed: {c}")
    if subset[FEATURES + EXTRA_FEATURES].isna().any().any():
        raise ValueError("Additional features unavailable; do not silently change the evaluation cohort")
    subset["stage"] = development_stages(subset)
    development = subset.loc[subset.stage.isin(DEVELOPMENT)].copy()
    final = subset.loc[subset.stage.isin(["test", "holdout_station"])].copy()
    assert_disjoint({p: development[development.stage.eq(p)] for p in DEVELOPMENT})
    development.to_parquet(out / "development.parquet", index=False)
    final.to_parquet(out / "evaluation_holdout.parquet", index=False)
    subset[["station_id", "date", "stage", "selection_hash"]].to_csv(out / "row_manifest.csv", index=False)
    summary = subset.groupby("stage")[TARGET].agg(rows="count", positives="sum", prevalence="mean")
    summary.to_csv(out / "partition_summary.csv")
    held = set(final.loc[final.stage.eq("holdout_station"), "station_id"])
    seen = set(development.station_id)
    if held & seen or held != set(HOLDOUT_STATIONS):
        raise ValueError("Entire station holdout failed")
    checks = {
        "same_30000_keys_and_baseline_features": True, "baseline_files_read_only": True,
        "duplicate_keys": 0, "entirely_held_out_stations": sorted(held),
        "feature_count_baseline": len(FEATURES), "feature_count_hydrology": len(FEATURES + EXTRA_FEATURES),
        "unknown_labels_excluded": report["unknown_24h"], "observed_rows_before_sampling": report["screened_label_rows"],
        "label_truth": "Observed proxy negatives, not verified physical absence; positive-only and unknown regimes excluded",
        "label_source_check": "Label-generation code/coverage checked; underlying satellite/event archive observations not independently verified",
        "windows": "t+1 target only; 3-day embargo at every development boundary; past-only rolling histories may legitimately cross a boundary",
        "availability": "24h rainfall is source daily rainfall; 72h/7-day totals are trailing inclusive 3/7 complete days. Reanalysis release latency/source timezone unverified; historical replay only",
        "class_imbalance": "No evaluation resampling or class weights; balanced weights only compete during base-model fitting",
        "residual_dependence": "Adjacent flood days, overlapping past windows and nearby virtual gauges share events/model grids; rows are not independent trials",
        "test_reuse": plan["reuse_caveat"],
        "excluded_features": "flood_byStor and its histories/missing flags, all horizons/regimes, future targets, station IDs/names/date in X",
    }
    write_json(out / "split_audit.json", checks)
    feature_audit = []
    for name in FEATURE_SETS["hydrology"]:
        values = subset[name]
        feature_audit.append(dict(feature=name, missing=int(values.isna().sum()), minimum=float(values.min()), maximum=float(values.max()),
                                  availability="Static terrain/coordinate" if name in ["elevation_m", "hand_m", "latitude", "longitude"] else "Closed historical feature day or named prior days; no future shift"))
    pd.DataFrame(feature_audit).to_csv(out / "feature_audit.csv", index=False)
    shutil.copy2(baseline / "classifier.joblib", out / "original_baseline.joblib")
    shutil.copy2(baseline / "thresholds.json", out / "original_thresholds.json")
    write_json(out / "audit_complete.json", {"plan_sha256": sha256(out / "plan.json"),
        "development_sha256": sha256(out / "development.parquet"), "evaluation_holdout_sha256": sha256(out / "evaluation_holdout.parquet")})
    print(summary.to_string(), flush=True)


def plot_validation(predictions, models, out, primary=None):
    selection = predictions[predictions.stage.eq("selection")]
    table = pd.read_csv(out / "selection_metrics.csv")
    displayed = ["original_baseline"]
    # Always show paired C=1 weighted/unweighted LR on unchanged inputs.
    displayed += [n for n in models if n.startswith("fixed_C1__baseline")]
    displayed += table.sort_values("brier").model_id.head(3).tolist()
    if primary: displayed.append(primary)
    displayed = list(dict.fromkeys(displayed))
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    bins = []
    for name in displayed:
        p = selection[name].to_numpy(); y = selection[TARGET].to_numpy()
        precision, recall, _ = precision_recall_curve(y, p)
        label = name.replace("__", "/")
        axes[0].plot(recall, precision, label=label)
        points = reliability(y, p)
        for row in points: bins.append({"model_id": name, **row})
        axes[1].plot([r["mean_probability"] for r in points], [r["positive_fraction"] for r in points], marker="o", label=label)
        axes[2].hist(p, bins=np.linspace(0, 1, 21), histtype="step", label=label)
    axes[0].axhline(selection[TARGET].mean(), color="gray", linestyle="--")
    axes[0].set(xlabel="Recall", ylabel="Precision", title="Model-selection validation: 2023 H1")
    axes[0].legend(fontsize=5)
    axes[1].plot([0, 1], [0, 1], "--", color="gray")
    axes[1].set(xlabel="Mean predicted probability", ylabel="Source proxy flood fraction", title="Validation calibration (10 equal-width bins)")
    axes[2].set(xlabel="Predicted probability", ylabel="Rows (log scale)", title="Validation score distribution", yscale="log")
    fig.tight_layout(); fig.savefig(out / "validation_pr_calibration.png", dpi=160); plt.close(fig)
    pd.DataFrame(bins).to_csv(out / "validation_reliability_bins.csv", index=False)


def fit_stage(out):
    if (out / "fit_complete.json").exists(): raise ValueError("Fitting already completed; refusing overwrite")
    baseline, plan = verify_baseline(out)
    data, parts = load_development(out)
    candidates_dir = out / "candidates"; candidates_dir.mkdir(exist_ok=True)
    searches, winners, fixed = [], {}, {}
    for i, spec in enumerate(plan["search"]):
        features = FEATURE_SETS[spec["feature_set"]]
        start = time.monotonic()
        fitted = pipeline(estimator(spec)).fit(parts["train"][features], parts["train"][TARGET].astype(int))
        p = fitted.predict_proba(parts["tuning"][features])[:, 1]
        ap = float(average_precision_score(parts["tuning"][TARGET], p))
        group = "__".join([spec["family"], spec["feature_set"], "balanced" if spec["balanced"] else "unweighted"])
        searches.append({"search_id": i, "group": group, "parameters": spec["parameters"], "tuning_ap": ap,
                         "tuning": score(parts["tuning"][TARGET], p), "seconds": time.monotonic() - start})
        if group not in winners or ap > winners[group][0]: winners[group] = (ap, fitted, spec)
        if spec["family"] == "logistic" and spec["feature_set"] == "baseline" and spec["parameters"]["C"] == 1.:
            fixed["fixed_C1__baseline__" + ("balanced" if spec["balanced"] else "unweighted")] = (ap, fitted, spec)
        print(f"[{i+1}/{len(plan['search'])}] {group} {spec['parameters']} tuning AP={ap:.4f}", flush=True)
    write_json(out / "hyperparameter_search.json", searches)
    pd.DataFrame([{k: v for k, v in row.items() if k != "tuning"} for row in searches]).to_csv(out / "hyperparameter_search.csv", index=False)
    winners.update(fixed)
    original = joblib.load(baseline / "classifier.joblib")
    predictions = data[["date", "station_id", "stage", TARGET]].copy()
    predictions["original_baseline"] = original.predict_proba(data[FEATURES])[:, 1]
    models = {"original_baseline": {"file": "original_baseline.joblib", "features": FEATURES,
                                    "method": "none", "family": "logistic", "base_id": "original_baseline", "feature_set": "baseline", "balanced": True}}
    for base_id, (_, fitted, spec) in winners.items():
        features = FEATURE_SETS[spec["feature_set"]]
        joblib.dump(fitted, candidates_dir / f"{base_id}__base.joblib")
        for method in ("none", "sigmoid", "isotonic"):
            model_id = base_id + "__" + method
            model = calibrated(fitted, parts["calibration"], features, method)
            destination = candidates_dir / f"{model_id}.joblib"
            joblib.dump(model, destination)
            predictions[model_id] = model.predict_proba(data[features])[:, 1]
            models[model_id] = {"file": str(destination.relative_to(out)), "features": features,
                                "method": method, "family": spec["family"], "base_id": base_id,
                                "feature_set": spec["feature_set"], "balanced": spec["balanced"], "parameters": spec["parameters"]}
    predictions.to_parquet(out / "development_predictions.parquet", index=False)
    rows = []
    for name in models:
        for stage in DEVELOPMENT:
            part = predictions[predictions.stage.eq(stage)]
            rows.append({"model_id": name, "stage": stage, **score(part[TARGET], part[name])})
    table = pd.DataFrame(rows)
    table.to_csv(out / "development_metrics.csv", index=False)
    table[table.stage.eq("selection")].to_csv(out / "selection_metrics.csv", index=False)
    write_json(out / "candidate_models.json", models)
    plot_validation(predictions, models, out)
    fit_clustering(parts["train"], out)
    write_json(out / "fit_complete.json", {"candidate_count": len(models), "plan_sha256": sha256(out / "plan.json"),
                                          "development_sha256": sha256(out / "development.parquet"),
                                          "predictions_sha256": sha256(out / "development_predictions.parquet"),
                                          "selection_metrics_sha256": sha256(out / "selection_metrics.csv"),
                                          "candidate_models_sha256": sha256(out / "candidate_models.json"),
                                          "code_sha256": {name: sha256(Path(__file__).parent / name) for name in ["training02.py", "refinement.py"]},
                                          "note": "No evaluation_holdout.parquet read during fitting/tuning/calibration"})


def fit_clustering(train, out):
    columns = BASE + ["rainfall_local_mm_sum3d", "rainfall_upstream_mm_sum7d", "river_discharge_m3s_mean7d"]
    preparation = Pipeline([("log1p", FunctionTransformer(np.log1p, feature_names_out="one-to-one")), ("scale", StandardScaler())])
    x = preparation.fit_transform(train[columns])
    comparisons, best = [], None
    for k in (2, 3, 4, 5, 6):
        kmeans = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(x)
        silhouette = float(silhouette_score(x, kmeans.labels_, sample_size=min(2000, len(x)), random_state=SEED))
        comparisons.append({"k": k, "silhouette": silhouette, "inertia": float(kmeans.inertia_)})
        if best is None or silhouette > best[0]: best = (silhouette, kmeans)
    kmeans = best[1]
    model = Pipeline([("preprocessing", preparation), ("kmeans", kmeans)])
    joblib.dump({"pipeline": model, "features": columns}, out / "clustering.joblib")
    write_json(out / "clustering.json", {"comparison": comparisons, "selected_k": kmeans.n_clusters, "features": columns,
        "selection": "Training-only silhouette of log1p-standardized hydrometeorology, without labels",
        "interpretation": "Incidence is post-hoc association with source proxy labels; cluster IDs are arbitrary, never validated risk categories",
        "hdbscan": "Optional method not run; this study uses a fixed train-only KMeans model with out-of-sample predict"})
    train.assign(cluster=kmeans.labels_).groupby("cluster")[columns].mean().to_csv(out / "cluster_weather_profiles.csv")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].plot([r["k"] for r in comparisons], [r["silhouette"] for r in comparisons], marker="o")
    axes[0].set(xlabel="k", ylabel="Training silhouette", title="Training-only cluster selection")
    image = axes[1].imshow(kmeans.cluster_centers_, aspect="auto", cmap="coolwarm")
    axes[1].set_xticks(range(len(columns)), columns, rotation=75, ha="right", fontsize=7)
    axes[1].set_yticks(range(kmeans.n_clusters)); axes[1].set_ylabel("Arbitrary cluster ID")
    fig.colorbar(image, ax=axes[1], label="SD of log1p input")
    fig.tight_layout(); fig.savefig(out / "clustering.png", dpi=150); plt.close(fig)


def select_stage(out):
    if (out / "selection_lock.json").exists(): raise ValueError("Selection already locked; refusing overwrite")
    baseline, plan = verify_baseline(out)
    fit = read(out / "fit_complete.json")
    if fit["plan_sha256"] != sha256(out / "plan.json") or fit["development_sha256"] != sha256(out / "development.parquet"):
        raise ValueError("Plan or development data changed after fitting")
    for filename, field in [("development_predictions.parquet", "predictions_sha256"),
                             ("selection_metrics.csv", "selection_metrics_sha256"), ("candidate_models.json", "candidate_models_sha256")]:
        if sha256(out / filename) != fit[field]: raise ValueError("Validation artifacts changed after fitting")
    for name, expected in fit["code_sha256"].items():
        if sha256(Path(__file__).parent / name) != expected: raise ValueError("Experiment code changed after fitting")
    models = read(out / "candidate_models.json")
    predictions = pd.read_parquet(out / "development_predictions.parquet")
    table = pd.read_csv(out / "selection_metrics.csv")
    baseline_ap = float(table.loc[table.model_id.eq("original_baseline"), "pr_auc_average_precision"].iloc[0])
    winner = selection_choice(table, baseline_ap)
    write_json(out / "model_choice.json", {"model_id": winner, "criterion": plan["selection_rule"], "baseline_selection_ap": baseline_ap,
                                          "chosen_before_threshold_period_inspection": True})
    threshold_data = predictions[predictions.stage.eq("threshold")]
    original_threshold = read(baseline / "thresholds.json")["binary_threshold"]
    reference = score(threshold_data[TARGET], threshold_data.original_baseline, original_threshold)
    budget = reference["false_alerts_per_detection"]
    operating = threshold_table(threshold_data[TARGET], threshold_data[winner])
    operating.to_csv(out / "threshold_tradeoffs.csv", index=False)
    chosen = recall_budget_threshold(operating, budget)
    original_operating = threshold_table(threshold_data[TARGET], threshold_data.original_baseline)
    original_operating.to_csv(out / "original_threshold_tradeoffs.csv", index=False)
    original_recall = recall_budget_threshold(original_operating, budget)
    f1 = operating.sort_values(["f1", "threshold"], ascending=[False, False]).iloc[0].to_dict()
    scenarios = []
    for miss_cost in (1., 2., 5., 10.):
        costs = operating.fp + miss_cost * operating.fn
        i = costs.idxmin()
        point = {key: None if isinstance(value, float) and not np.isfinite(value) else value for key, value in operating.loc[i].to_dict().items()}
        scenarios.append({"miss_to_false_alert_cost": miss_cost, "selected": False, **point, "validation_cost": float(costs.loc[i])})
    write_json(out / "cost_sensitivity.json", {"note": "Exploratory cost assumptions, not approved warning policies or model-selection criteria", "scenarios": scenarios})
    config = {"binary_threshold": float(chosen["threshold"]), "selected_on": "2023 H2 validation only; baseline FP/TP budget",
              "presentation_tiers": TIERS, "presentation_status": "Provisional research presentation tiers, not calibrated safety thresholds",
              "false_alerts_per_detection_budget": budget, "baseline_validation": reference,
              "selected_validation_operating_point": chosen, "f1_comparison_threshold": f1["threshold"],
              "original_baseline_recall_threshold": original_recall["threshold"], "original_baseline_threshold": original_threshold,
              "tradeoff": "Ratio constraint does not cap absolute FP; counts and per-1000 rates are reported separately"}
    write_json(out / "thresholds.json", config)
    shutil.copy2(out / models[winner]["file"], out / "classifier.joblib")
    schema = read(baseline / "feature_schema.json")
    schema.update(features=models[winner]["features"], required=models[winner]["features"],
                  signed_features=[f for f in models[winner]["features"] if f.startswith(("discharge_change", "discharge_relative", "soil_water_change"))])
    write_json(out / "feature_schema.json", schema)
    plot_thresholds(operating, chosen, reference, out)
    plot_validation(predictions, models, out, winner)
    feature_importances(out, models[winner])
    write_json(out / "selection_lock.json", {"model_id": winner, "plan_sha256": sha256(out / "plan.json"),
        "classifier_sha256": sha256(out / "classifier.joblib"), "thresholds_sha256": sha256(out / "thresholds.json"),
        "feature_schema_sha256": sha256(out / "feature_schema.json"),
        "evaluation_holdout_sha256": read(out / "audit_complete.json")["evaluation_holdout_sha256"],
        "code_sha256": {name: sha256(Path(__file__).parent / name) for name in ["training02.py", "refinement.py"]},
        "locked_at": datetime.now(timezone.utc).isoformat()})
    print(json.dumps({"winner": winner, "false_alert_budget": budget, "threshold": config["binary_threshold"],
                      "validation_baseline": reference, "validation_selected": chosen}, indent=2), flush=True)


def plot_thresholds(table, chosen, reference, out):
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    axes[0].plot(table.threshold, table.recall, label="Recall"); axes[0].plot(table.threshold, table.precision, label="Precision")
    axes[0].axvline(chosen["threshold"], linestyle="--", color="black"); axes[0].legend()
    axes[0].set(xlabel="Probability threshold", ylabel="Metric", title="Threshold validation: 2023 H2")
    axes[1].plot(table.recall, table.false_alerts_per_1000)
    axes[1].scatter([reference["recall"], chosen["recall"]], [reference["false_alerts_per_1000"], chosen["false_alerts_per_1000"]], c=["gray", "red"])
    axes[1].set(xlabel="Recall", ylabel="False alerts per 1,000 rows", title="Gray: baseline; red: selected")
    finite = table[np.isfinite(table.false_alerts_per_detection)]
    axes[2].plot(finite.recall, finite.false_alerts_per_detection)
    axes[2].axhline(reference["false_alerts_per_detection"], color="black", linestyle="--", label="Baseline FP/TP budget")
    axes[2].set(xlabel="Recall", ylabel="False alerts / detection", ylim=(0, max(5, 2*reference["false_alerts_per_detection"])))
    axes[2].legend(fontsize=8)
    fig.tight_layout(); fig.savefig(out / "validation_threshold_tradeoffs.png", dpi=160); plt.close(fig)


def feature_importances(out, selected):
    data, parts = load_development(out)
    model = joblib.load(out / "classifier.joblib")
    permutation = permutation_importance(model, parts["selection"][selected["features"]], parts["selection"][TARGET],
                                         scoring="average_precision", n_repeats=5, random_state=SEED, n_jobs=1)
    table = pd.DataFrame({"feature": selected["features"], "validation_ap_drop": permutation.importances_mean,
                          "repeat_sd": permutation.importances_std}).sort_values("validation_ap_drop", ascending=False)
    table.to_csv(out / "validation_permutation_importance.csv", index=False)
    base_path = out / "candidates" / (selected["base_id"] + "__base.joblib")
    base = joblib.load(base_path) if base_path.exists() else model
    classifier = base.named_steps["classifier"]
    values = classifier.coef_[0] if hasattr(classifier, "coef_") else classifier.feature_importances_
    pd.DataFrame({"feature": selected["features"], "native_importance_or_scaled_coefficient": values}).to_csv(out / "native_feature_importance.csv", index=False)
    fig, ax = plt.subplots(figsize=(8, 6))
    top = table.head(16).iloc[::-1]
    ax.barh(top.feature, top.validation_ap_drop, xerr=top.repeat_sd)
    ax.set(xlabel="Selection-validation AP decrease (5 permutations)", title="Correlated features can share/mask importance")
    fig.tight_layout(); fig.savefig(out / "feature_importance.png", dpi=150); plt.close(fig)


def evaluate_stage(out):
    if (out / "evaluation.json").exists(): raise ValueError("Final evaluation already consumed; refusing overwrite")
    baseline, plan = verify_baseline(out)
    lock = read(out / "selection_lock.json")
    for filename, field in [("classifier.joblib", "classifier_sha256"), ("thresholds.json", "thresholds_sha256"),
                             ("feature_schema.json", "feature_schema_sha256"), ("plan.json", "plan_sha256"),
                             ("evaluation_holdout.parquet", "evaluation_holdout_sha256")]:
        if sha256(out / filename) != lock[field]: raise ValueError(f"Changed after selection lock: {filename}")
    for name, expected in lock["code_sha256"].items():
        if sha256(Path(__file__).parent / name) != expected: raise ValueError("Experiment code changed after selection lock")
    final = pd.read_parquet(out / "evaluation_holdout.parquet")
    development, _ = load_development(out)
    data = pd.concat([development, final], ignore_index=True)
    model, original = joblib.load(out / "classifier.joblib"), joblib.load(out / "original_baseline.joblib")
    features = read(out / "feature_schema.json")["features"]
    p = model.predict_proba(data[features])[:, 1]
    old = original.predict_proba(data[FEATURES])[:, 1]
    thresholds = read(out / "thresholds.json")
    policies = {"original_baseline": (old, thresholds["original_baseline_threshold"]),
                "baseline_threshold_only": (old, thresholds["original_baseline_recall_threshold"]),
                "selected_default_0_5": (p, .5), "selected_validation_f1": (p, thresholds["f1_comparison_threshold"]),
                "selected_recall_budget": (p, thresholds["binary_threshold"])}
    rows, per_station = [], []
    for policy, (probabilities, threshold) in policies.items():
        for stage in [*DEVELOPMENT, "test", "holdout_station"]:
            mask = data.stage.eq(stage).to_numpy()
            rows.append({"policy": policy, "stage": stage, "threshold": threshold, **score(data.loc[mask, TARGET], probabilities[mask], threshold)})
            if stage in ["test", "holdout_station"]:
                for station in sorted(data.loc[mask, "station_id"].unique()):
                    station_mask = mask & data.station_id.eq(station).to_numpy()
                    per_station.append({"policy": policy, "stage": stage, "station_id": station, **score(data.loc[station_mask, TARGET], probabilities[station_mask], threshold)})
    table = pd.DataFrame(rows); table.to_csv(out / "evaluation_table.csv", index=False)
    pd.DataFrame(per_station).to_csv(out / "per_station_metrics.csv", index=False)
    station = pd.DataFrame(per_station)
    original_stations = station[station.policy.eq("original_baseline")].set_index(["stage", "station_id"])
    chosen_stations = station[station.policy.eq("selected_recall_budget")].set_index(["stage", "station_id"])
    differences = chosen_stations[["precision", "recall", "f1", "pr_auc_average_precision", "brier"]] - original_stations[["precision", "recall", "f1", "pr_auc_average_precision", "brier"]]
    differences.to_csv(out / "per_station_differences.csv")
    old_evaluation = read(baseline / "evaluation.json")
    old_winner = old_evaluation["selected_by_validation_ap"]
    for stage in ["test", "holdout_station"]:
        actual = next(r for r in rows if r["policy"] == "original_baseline" and r["stage"] == stage)
        expected = old_evaluation["candidates"][old_winner][stage]
        for key in ["brier", "f1", "roc_auc", "pr_auc_average_precision"]:
            if not np.isclose(actual[key], expected[key]): raise ValueError("Original baseline did not reproduce on identical final rows")
    predictions = data[["date", "station_id", "stage", TARGET]].copy()
    predictions["original_baseline_probability"] = old; predictions["selected_probability"] = p
    predictions.to_parquet(out / "all_predictions.parquet", index=False)
    write_json(out / "evaluation.json", {"selected_model": lock["model_id"], "results": rows,
                                         "test_reuse_caveat": plan["reuse_caveat"], "baseline_files_unchanged": True})
    final_plots(data, policies, out)
    cluster_incidence(data, out)
    registry = read(baseline / "stations.json")
    test = data.loc[data.stage.eq("test")].copy(); test["probability"] = p[data.stage.eq("test")]
    examples = []
    for name, i in [("normal", test.probability.idxmin()), ("high_risk", test.probability.idxmax())]:
        row = test.loc[i]
        examples.append({"id": name, "selection": "Held-out score extreme chosen after frozen evaluation; not representative accuracy evidence",
            "station": registry[row.station_id], "country": "Bangladesh", "mode": "historical_replay", "feature_date": row.date.strftime("%Y-%m-%d"),
            "as_of": row.date.strftime("%Y-%m-%dT23:59:59Z"), "features": {c: float(row[c]) for c in features},
            "observed_proxy_label": int(row[TARGET]), "expected_probability": float(row.probability)})
    write_json(out / "replay_examples.json", examples)
    for name in ["stations.json", "provenance.json"]: shutil.copy2(baseline / name, out / name)
    metadata = read(baseline / "model_metadata.json")
    metadata.update(model_version="bd-research-02-" + sha256(out / "classifier.joblib")[:12], selected_model=lock["model_id"],
                    trained_at=datetime.now(timezone.utc).isoformat(), classifier_sha256=sha256(out / "classifier.joblib"),
                    python=platform.python_version(), calibration=read(out / "candidate_models.json")[lock["model_id"]]["method"],
                    selection_rule=plan["selection_rule"], test_reuse_caveat=plan["reuse_caveat"], smoke_only=False)
    metadata["versions"] = {name: importlib.metadata.version(name) for name in metadata["versions"]}
    write_json(out / "model_metadata.json", metadata)
    verify_baseline(out)
    write_json(out / "reproducibility.json", {"baseline_unchanged": True, "baseline_file_hashes": plan["baseline_file_hashes"],
        "selection_lock": lock, "development_sha256": sha256(out / "development.parquet"), "evaluation_sha256": sha256(out / "evaluation_holdout.parquet"),
        "threads": {"OMP_NUM_THREADS": 2, "OPENBLAS_NUM_THREADS": 2, "estimator_threads": 2},
        "versions": metadata["versions"], "python": platform.python_version(),
        "note": "No claim of an independent reproduction until a second new directory is actually run; final records remain excluded from all fit/selection stages"})
    print(table[table.stage.isin(["test", "holdout_station"])][["policy", "stage", "precision", "recall", "f1", "brier", "pr_auc_average_precision"]].to_string(index=False), flush=True)


def final_plots(data, policies, out):
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    for i, stage in enumerate(["test", "holdout_station"]):
        mask = data.stage.eq(stage).to_numpy(); y = data.loc[mask, TARGET]
        for name in ["original_baseline", "selected_recall_budget"]:
            p, _ = policies[name]; p = p[mask]
            precision, recall, _ = precision_recall_curve(y, p)
            axes[i, 0].plot(recall, precision, label=name)
            points = reliability(y, p)
            axes[i, 1].plot([r["mean_probability"] for r in points], [r["positive_fraction"] for r in points], marker="o", label=name)
        axes[i, 0].axhline(y.mean(), color="gray", linestyle="--"); axes[i, 0].legend(fontsize=7)
        axes[i, 0].set(title=stage + " PR curve", xlabel="Recall", ylabel="Precision")
        axes[i, 1].plot([0, 1], [0, 1], "--", color="gray"); axes[i, 1].set(title=stage + " reliability", xlabel="Mean probability", ylabel="Observed proxy fraction")
        p, threshold = policies["selected_recall_budget"]
        matrix = np.array(score(y, p[mask], threshold)["confusion_matrix_tn_fp_fn_tp"]).reshape(2, 2)
        axes[i, 2].imshow(matrix, cmap="Blues")
        for (r, c), count in np.ndenumerate(matrix): axes[i, 2].text(c, r, str(count), ha="center", va="center")
        axes[i, 2].set_xticks([0, 1]); axes[i, 2].set_yticks([0, 1])
        axes[i, 2].set(title="Selected recall-budget policy", xlabel="Predicted", ylabel="Source proxy label")
    fig.tight_layout(); fig.savefig(out / "final_comparison.png", dpi=160); plt.close(fig)


def cluster_incidence(data, out):
    bundle = joblib.load(out / "clustering.joblib")
    clusters = bundle["pipeline"].predict(data[bundle["features"]])
    assigned = data[["date", "station_id", "stage", TARGET]].copy(); assigned["cluster"] = clusters
    assigned.to_csv(out / "cluster_assignments.csv", index=False)
    incidence = assigned.groupby(["stage", "cluster"])[TARGET].agg(rows="count", positives="sum", incidence="mean")
    incidence.to_csv(out / "cluster_incidence.csv")
    fig, ax = plt.subplots(figsize=(9, 4))
    incidence.loc[["train", "selection", "threshold", "test", "holdout_station"]].incidence.unstack(0).plot.bar(ax=ax)
    ax.set(xlabel="Arbitrary cluster ID", ylabel="Source proxy positive fraction", title="Descriptive incidence; not validated flood-risk categories")
    fig.tight_layout(); fig.savefig(out / "cluster_incidence.png", dpi=150); plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["audit", "fit", "select", "evaluate", "report", "all"])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args()
    protect_paths(args.out, args.baseline)
    for stage in (["audit", "fit", "select", "evaluate", "report"] if args.stage == "all" else [args.stage]):
        if stage == "audit": audit_stage(args.out, args.baseline)
        elif stage == "fit": fit_stage(args.out)
        elif stage == "select": select_stage(args.out)
        elif stage == "evaluate": evaluate_stage(args.out)
        else:
            from ml.report02 import render
            render(args.out)


if __name__ == "__main__":
    main()
