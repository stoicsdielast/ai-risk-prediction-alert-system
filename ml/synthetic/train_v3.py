"""Synthetic v3: per-scenario baselines, time-safe inner-fold tuning, selection.

Protocol: docs/SYNTHETIC_V3_PROTOCOL.md (registered before this code ran).
Each scenario is trained and reported separately; nothing here touches the v1
or v2 runs, the v1 dataset or the deployed serving bundle.
"""
import argparse
import json
from pathlib import Path
import time

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import optuna
import pandas as pd
from sklearn.calibration import IsotonicRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_curve
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml.refinement import reliability, score, sha256
from ml.train import write_json
from ml.training03 import apply_sigmoid, fit_sigmoid
from ml.synthetic.features_v2 import build_features_v2
from ml.synthetic.generate import NOTICE
from ml.synthetic.metrics_v3 import block_bootstrap, evaluate
from ml.synthetic.train import BUDGET, EVALUATIONS, HELD_LOCATIONS, partition
from ml.synthetic.train_v2 import budget_values, fit_model, make_catboost, make_lightgbm, objective_value

optuna.logging.set_verbosity(optuna.logging.WARNING)

DEVELOPMENT = ["train", "calibration", "selection", "threshold"]
INNER_FOLDS = 3
INNER_EMBARGO_HOURS = 24
STORM_TAIL_HOURS = 168
OPTUNA_TRIALS = {"catboost": 24, "lightgbm": 18}
OPTUNA_TIMEOUT = {"catboost": 1500, "lightgbm": 900}
TOP_K = 5


def inner_splits(train, scenarios, k=INNER_FOLDS):
    """Chronological rolling-origin folds with storm grouping.

    The training window is cut into ``k + 1`` contiguous day blocks: block 0 is
    the fitting prefix and fold ``i`` validates on block ``i + 1`` while fitting
    on every earlier block (minus a 24 h embargo). Any storm whose span started
    before the validation block but reaches into it is removed from that block's
    validation rows, so one flood episode never contributes to both fitting and
    validation.
    """
    days = np.array(sorted(pd.to_datetime(train.timestamp).dt.floor("D").unique()))
    blocks = np.array_split(days, k + 1)
    # pandas 3 stores us resolution; normalise to ns so epoch arithmetic matches
    # Timestamp.value and the v1/v2 event-metric convention.
    times = train.timestamp.to_numpy(dtype="datetime64[ns]").astype("int64")
    spans = [(storm.start.value - INNER_EMBARGO_HOURS * 3600 * 10**9,
              storm.end.value + STORM_TAIL_HOURS * 3600 * 10**9)
             for storm in scenarios.itertuples()]
    folds = []
    for index in range(k):
        block = blocks[index + 1]
        start, end = pd.Timestamp(block[0]).value, pd.Timestamp(block[-1]).value + 24 * 3600 * 10**9 - 1
        fit = times < (start - INNER_EMBARGO_HOURS * 3600 * 10**9)
        in_block = (times >= start) & (times <= end)
        crossing = np.zeros(len(train), dtype=bool)
        for a, b in spans:
            if a <= start <= b:
                crossing |= (times >= a) & (times <= b)
        validation = in_block & ~crossing
        fold = {"fold": index, "fit": train[fit].copy(), "validation": train[validation].copy(),
                "validation_excluded_storm_rows": int((in_block & crossing).sum())}
        for side in ("fit", "validation"):
            if fold[side].flood_within_24h.nunique() != 2:
                raise ValueError(f"Inner fold {index} has a single class in {side}")
        folds.append(fold)
    return folds


def fold_objective(family, params, folds, names):
    scores = []
    for fold in folds:
        model = fit_model(family, params, fold["fit"], fold["validation"], names)
        p = model.predict_proba(fold["validation"][names])[:, 1]
        scores.append(objective_value(fold["validation"].flood_within_24h, p))
        del model
    return float(np.mean(scores))


def tune_family(family, folds, names, out):
    storage = {}

    def objective(trial):
        if family == "catboost":
            params = {"depth": trial.suggest_int("depth", 4, 8),
                      "learning_rate": trial.suggest_float("learning_rate", .015, .12, log=True),
                      "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1., 20., log=True),
                      "iterations": 900,
                      "random_strength": trial.suggest_float("random_strength", 0., 2.),
                      "bagging_temperature": trial.suggest_float("bagging_temperature", 0., 1.),
                      "border_count": trial.suggest_categorical("border_count", [64, 128, 254]),
                      "auto_class_weights": trial.suggest_categorical("auto_class_weights", ["Balanced", None])}
        else:
            params = {"num_leaves": trial.suggest_int("num_leaves", 8, 64),
                      "max_depth": trial.suggest_int("max_depth", 3, 10),
                      "learning_rate": trial.suggest_float("learning_rate", .015, .12, log=True),
                      "min_child_samples": trial.suggest_int("min_child_samples", 10, 80),
                      "subsample": trial.suggest_float("subsample", .6, 1.), "subsample_freq": 1,
                      "colsample_bytree": trial.suggest_float("colsample_bytree", .6, 1.),
                      "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 20., log=True),
                      "class_weight": trial.suggest_categorical("class_weight", ["balanced", None])}
        value = fold_objective(family, params, folds, names)
        storage[trial.number] = {"params": params, "objective": value}
        return value

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=314))
    study.optimize(objective, n_trials=OPTUNA_TRIALS[family], timeout=OPTUNA_TIMEOUT[family],
                   n_jobs=1, gc_after_trial=True)
    rows = [{"trial": t.number, "value": t.value, **t.params, "state": str(t.state)} for t in study.trials]
    pd.DataFrame(rows).to_csv(out / f"optuna_trials_{family}.csv", index=False)
    ranked = sorted(storage.values(), key=lambda r: r["objective"], reverse=True)[:TOP_K]
    print(f"{family}: {len(study.trials)} trials, best inner-fold objective {study.best_value:.4f}", flush=True)
    return ranked


def predict_all(model, parts, names):
    return {s: model.predict_proba(d[names])[:, 1] for s, d in parts.items()}


def load_dataset(dataset):
    meta = json.loads((dataset / "dataset_metadata.json").read_text())
    return (meta,
            pd.read_csv(dataset / "locations.csv"),
            pd.read_parquet(dataset / "weather_observations.parquet"),
            pd.read_parquet(dataset / "training_labels.parquet"),
            pd.read_csv(dataset / "simulation_scenarios.csv", parse_dates=["start", "end"]),
            pd.read_csv(dataset / "flood_events.csv", parse_dates=["event_start", "event_end"]))


def prepare(dataset):
    meta, loc, obs, labels, scenarios, events = load_dataset(dataset)
    features, extended, weather_only = build_features_v2(obs, loc, meta["config"]["frequency"])
    frame = features.merge(labels, on=["location_id", "timestamp"], validate="one_to_one")
    frame["stage"], reserved = partition(frame, scenarios)
    parts = {s: frame[frame.stage.eq(s)].copy() for s in DEVELOPMENT + EVALUATIONS}
    for s in DEVELOPMENT:
        if parts[s].flood_within_24h.nunique() != 2:
            raise ValueError(f"Insufficient classes in {s}")
    return meta, features, extended, weather_only, frame, parts, scenarios, events, reserved


def run(dataset, out):
    if out.exists():
        raise ValueError("Run exists; use a fresh output directory")
    meta, features, extended, weather_only, frame, parts, scenarios, events, reserved = prepare(dataset)
    out.mkdir(parents=True)
    features.to_parquet(out / "features.parquet", index=False)
    frame[["location_id", "timestamp", "stage", "flood_within_24h", "flood_occurred", "forecast_eligible"]].to_parquet(
        out / "splits.parquet", index=False)
    frame.groupby("stage").agg(rows=("stage", "size"), positives=("flood_within_24h", "sum")).to_csv(
        out / "partition_summary.csv")

    folds = inner_splits(parts["train"], scenarios)
    fold_manifest = [{"fold": f["fold"], "fit_rows": len(f["fit"]), "validation_rows": len(f["validation"]),
                      "fit_positive": int(f["fit"].flood_within_24h.sum()),
                      "validation_positive": int(f["validation"].flood_within_24h.sum()),
                      "fit_end": str(f["fit"].timestamp.max()),
                      "validation_start": str(f["validation"].timestamp.min()),
                      "validation_end": str(f["validation"].timestamp.max()),
                      "validation_excluded_storm_rows": f["validation_excluded_storm_rows"]} for f in folds]
    write_json(out / "inner_folds.json", {"n_folds": INNER_FOLDS, "embargo_hours": INNER_EMBARGO_HOURS,
                                          "storm_tail_hours": STORM_TAIL_HOURS,
                                          "grouping": "storm spans reaching into a validation block are dropped from that block",
                                          "folds": fold_manifest})
    write_json(out / "protocol.json", {
        "source_type": "synthetic", "notice": NOTICE, "scenario": meta["config"]["scenario"],
        "dataset": str(dataset.resolve()), "dataset_version": meta["dataset_version"],
        "dataset_metadata_sha256": sha256(dataset / "dataset_metadata.json"),
        "extended_features": extended, "weather_only_features": weather_only,
        "held_location_ids": HELD_LOCATIONS, "reserved_storms": reserved,
        "false_alerts_per_detection_budget": BUDGET,
        "inner_folds": INNER_FOLDS, "optuna_trials": OPTUNA_TRIALS, "optuna_timeout_seconds": OPTUNA_TIMEOUT,
        "objective": "Mean budget-feasible recall across inner folds, tie-break mean AP then F2; infeasible folds score -1",
        "selection": "Top-5 calibration configs per family, refit on train with early stopping on calibration, "
                     "re-evaluated on selection with fresh budget thresholds; winner by selection recall under "
                     "budget, then AP, F1, Brier",
        "calibration": "none vs sigmoid vs isotonic fit on 2023 H1, compared on 2023 H2 by ECE(10) then Brier",
        "threshold": "budget policy on the 2024 H1 threshold partition only",
        "diagnostic_partitions": EVALUATIONS, "seed": 314, "protocol_document": "docs/SYNTHETIC_V3_PROTOCOL.md"})

    candidates, fitted = {}, {}

    def top_configs(family, ranked):
        return [{"params": e["params"], "model": fit_model(family, e["params"], parts["train"], parts["calibration"], extended)}
                for e in ranked]

    family_top = {}
    for family in ["catboost", "lightgbm"]:
        ranked = tune_family(family, folds, extended, out)
        family_top[family] = top_configs(family, ranked)
        for rank, entry in enumerate(family_top[family]):
            name = f"{family}_tuned{rank + 1}"
            candidates[name] = {"family": family, "params": entry["params"], "features": extended,
                                "model": entry["model"], "calibration": "none", "rank": rank}
            fitted[name] = entry["model"]

    baselines = {
        "logistic_baseline": LogisticRegression(C=1., class_weight="balanced", max_iter=1500, random_state=314),
        "random_forest_baseline": RandomForestClassifier(n_estimators=160, max_depth=14, min_samples_leaf=10,
                                                         class_weight="balanced_subsample", n_jobs=4, random_state=314),
    }
    for name, estimator in baselines.items():
        model = Pipeline([("imputer", SimpleImputer(strategy="median", add_indicator=True)),
                          ("scale", StandardScaler()), ("classifier", estimator)])
        model.fit(parts["train"][extended], parts["train"].flood_within_24h.astype(int))
        candidates[name] = {"family": "sklearn", "params": {}, "features": extended, "model": model,
                            "calibration": "none", "rank": 0}

    for name, source in [("catboost_weather_only", "catboost_tuned1"), ("lightgbm_weather_only", "lightgbm_tuned1")]:
        family = candidates[source]["family"]
        model = fit_model(family, dict(candidates[source]["params"]), parts["train"], parts["calibration"], weather_only)
        candidates[name] = {"family": family, "params": candidates[source]["params"], "features": weather_only,
                            "model": model, "calibration": "none", "rank": 0, "weather_only": True}

    for name, entry in candidates.items():
        entry["probabilities"] = predict_all(entry["model"], parts, entry["features"])

    selection_rows = []
    for name, entry in candidates.items():
        d, p = parts["selection"], entry["probabilities"]["selection"]
        point = budget_values(d.flood_within_24h, p)
        row = {"candidate": name, "family": entry["family"], "weather_only": entry.get("weather_only", False),
               "feasible": point is not None,
               "threshold": float(point["threshold"]) if point else float(np.nextafter(1., 2.))}
        row.update(evaluate(d, p, row["threshold"], events, include_bootstrap=False))
        selection_rows.append({k: v for k, v in row.items() if not isinstance(v, dict)})
    selection = pd.DataFrame(selection_rows)
    selection.to_csv(out / "selection_metrics.csv", index=False)
    feasible = selection[selection.feasible].sort_values(
        ["recall", "pr_auc_average_precision", "f1", "brier", "candidate"],
        ascending=[False, False, False, True, True])
    if feasible.empty:
        raise ValueError("No candidate meets the validation false-alert budget")
    winner = feasible.iloc[0].candidate
    write_json(out / "selection_lock.json", {"selected": winner, "dataset_sha256": sha256(dataset / "dataset_metadata.json"),
                                             "selection_table_sha256": sha256(out / "selection_metrics.csv"),
                                             "selected_before_threshold_scoring": True})
    print("Selected on selection partition:", winner, flush=True)

    entry = candidates[winner]
    y_cal = parts["calibration"].flood_within_24h
    calibrators = {"none": None, "sigmoid": fit_sigmoid(entry["probabilities"]["calibration"], y_cal),
                   "isotonic": IsotonicRegression(out_of_bounds="clip").fit(entry["probabilities"]["calibration"], y_cal)}
    cal_rows = []
    for method, calibrator in calibrators.items():
        probs = {}
        for stage in DEVELOPMENT + EVALUATIONS:
            raw = entry["probabilities"][stage]
            probs[stage] = raw if calibrator is None else (
                apply_sigmoid(calibrator, raw) if method == "sigmoid" else calibrator.predict(raw))
        point = budget_values(parts["selection"].flood_within_24h, probs["selection"])
        row = {"method": method, "feasible": point is not None,
               "threshold": float(point["threshold"]) if point else float(np.nextafter(1., 2.))}
        row.update(score(parts["selection"].flood_within_24h, probs["selection"], row["threshold"]))
        cal_rows.append(row)
        entry.setdefault("method_probabilities", {})[method] = probs
    calibration_table = pd.DataFrame([{k: v for k, v in r.items() if not isinstance(v, dict)} for r in cal_rows])
    calibration_table.to_csv(out / "calibration_comparison.csv", index=False)
    valid = calibration_table[calibration_table.feasible].sort_values(["ece_equal_width_10_bins", "brier", "method"])
    method = valid.iloc[0].method if not valid.empty else "none"
    entry["calibration"] = method
    entry["probabilities"] = entry["method_probabilities"][method]
    entry["calibrator"] = calibrators[method]
    print("Calibration method chosen on selection:", method, flush=True)

    operating_thresholds = {}
    for name, e in candidates.items():
        point = budget_values(parts["threshold"].flood_within_24h, e["probabilities"]["threshold"])
        operating_thresholds[name] = {"threshold": float(point["threshold"]) if point else float(np.nextafter(1., 2.)),
                                      "feasible": point is not None}
    write_json(out / "thresholds.json", operating_thresholds)

    rows, per_location, saved, bootstraps = [], [], [], {}
    for name, e in candidates.items():
        threshold = operating_thresholds[name]["threshold"]
        for stage in DEVELOPMENT + EVALUATIONS:
            d, p = parts[stage], e["probabilities"][stage]
            record = {"candidate": name, "stage": stage, "threshold": threshold,
                      **evaluate(d, p, threshold, events, include_bootstrap=False)}
            rows.append({k: v for k, v in record.items() if not isinstance(v, dict)})
            if stage in EVALUATIONS:
                for location_id, group in d.groupby("location_id"):
                    mask = d.location_id.eq(location_id).to_numpy()
                    located = {k: v for k, v in evaluate(group, p[mask], threshold, events,
                                                         include_bootstrap=False, include_episodes=False).items()
                               if not isinstance(v, dict)}
                    per_location.append({"candidate": name, "stage": stage, "location_id": location_id,
                                         "threshold": threshold, **located})
            saved.append(d[["location_id", "timestamp", "flood_within_24h"]].assign(
                candidate=name, stage=stage, probability=p, threshold=threshold))
            if name == winner and stage in EVALUATIONS:
                bootstraps[stage] = block_bootstrap(d, p, threshold)
    pd.DataFrame(rows).to_csv(out / "metrics.csv", index=False)
    pd.DataFrame(per_location).to_csv(out / "per_location_metrics.csv", index=False)
    pd.concat(saved, ignore_index=True).to_parquet(out / "predictions.parquet", index=False)
    write_json(out / "bootstrap_intervals.json", bootstraps)

    estimator = entry["model"]
    if isinstance(estimator, Pipeline):
        estimator = estimator.named_steps["classifier"]
    importance = getattr(estimator, "feature_importances_", None)
    if importance is None and hasattr(estimator, "coef_"):
        importance = np.abs(estimator.coef_[0])
    if importance is not None:
        pd.DataFrame({"feature": entry["features"], "importance": importance}).sort_values(
            "importance", ascending=False).to_csv(out / "feature_importance.csv", index=False)

    write_json(out / "best_params.json", {name: {"family": e["family"], "params": e["params"],
                                                  "features": "extended" if e["features"] == extended else "weather_only",
                                                  "calibration": e.get("calibration", "none")}
                                           for name, e in candidates.items()})
    save_bundle(dataset, out, winner, entry, operating_thresholds[winner]["threshold"], extended, weather_only, meta)
    plot_results(out, parts, {n: e["probabilities"] for n, e in candidates.items()},
                 {n: operating_thresholds[n]["threshold"] for n in candidates}, winner)
    summary = {"scenario": meta["config"]["scenario"], "winner": winner, "method": method,
               "threshold": operating_thresholds[winner]["threshold"],
               "n_extended_features": len(extended), "n_weather_only_features": len(weather_only),
               "inner_folds": fold_manifest}
    write_json(out / "run_summary.json", summary)
    return summary


def save_bundle(dataset, out, winner, entry, threshold, extended, weather_only, meta):
    names = entry["features"]
    names = extended if names == extended else weather_only if names == weather_only else names
    bundle = {"model": entry["model"], "calibrator": entry.get("calibrator"), "calibration": entry.get("calibration", "none"),
              "features": names, "threshold": float(threshold),
              "model_version": f"synthetic-fiji-v3-{meta['config']['scenario']}-{winner}__{entry.get('calibration', 'none')}",
              "scenario": meta["config"]["scenario"], "source_type": "synthetic", "notice": NOTICE}
    model_path = out / "candidate_model.joblib"
    joblib.dump(bundle, model_path)
    labels = pd.read_parquet(Path(dataset) / "training_labels.parquet", columns=["location_id", "timestamp", "flood_occurred"])
    labels.to_parquet(out / "simulation_outcomes.parquet", index=False)
    write_json(out / "candidate_metadata.json", {
        "model_version": bundle["model_version"], "selected_candidate": winner, "scenario": bundle["scenario"],
        "calibration": bundle["calibration"], "threshold": float(threshold), "source_type": "synthetic",
        "notice": NOTICE, "features": names, "n_features": len(names), "model_sha256": sha256(model_path),
        "research_only": True,
        "note": "Scenario research candidate; the deployed model is unchanged. Promotion requires explicit human approval."})


def plot_results(out, parts, probabilities, thresholds, winner):
    bins = []
    for stage in ["selection", "threshold"] + EVALUATIONS:
        d = parts[stage]
        fig, axes = plt.subplots(1, 2, figsize=(13, 5))
        for candidate, probs in probabilities.items():
            p = probs[stage]
            if d.flood_within_24h.sum() and d.flood_within_24h.nunique() == 2:
                precision, recall, _ = precision_recall_curve(d.flood_within_24h, p)
                axes[0].plot(recall, precision, label=candidate, alpha=.7)
            for r in reliability(d.flood_within_24h, p):
                bins.append({"candidate": candidate, "stage": stage, **r})
        axes[0].set(xlabel="Recall", ylabel="Precision", title=f"{stage} — simulator outcomes ({winner} highlighted)")
        axes[0].legend(fontsize=5)
        for candidate, probs in list(probabilities.items())[:6]:
            rel = reliability(d.flood_within_24h, probs[stage])
            axes[1].plot([r["mean_probability"] for r in rel], [r["positive_fraction"] for r in rel],
                         marker=".", label=candidate)
        axes[1].plot([0, 1], [0, 1], "k--")
        axes[1].set(xlabel="Predicted probability", ylabel="Simulated incidence", title="Calibration")
        fig.tight_layout()
        fig.savefig(out / f"{stage}_pr_calibration.png", dpi=160)
        plt.close(fig)
    pd.DataFrame(bins).to_csv(out / "calibration_bins.csv", index=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    result = run(args.dataset, args.out)
    write_json(args.out / "run_timing.json", {"total_seconds": time.monotonic() - started, **result})
