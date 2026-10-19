"""Synthetic v2: Optuna tuning, validation-only selection, diagnostic evaluation.

Protocol: docs/SYNTHETIC_V2_PROTOCOL.md. The reserved independent-seed
evaluations (ml/data/synthetic_fiji/v2-reserved-*) are NOT touched here.
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
from sklearn.metrics import (accuracy_score, average_precision_score, balanced_accuracy_score,
                             log_loss, precision_recall_curve, roc_auc_score)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml.refinement import recall_budget_threshold, reliability, score, threshold_table, sha256
from ml.train import write_json
from ml.training03 import apply_sigmoid, fit_sigmoid
from ml.synthetic.features_v2 import build_features_v2
from ml.synthetic.generate import NOTICE
from ml.synthetic.train import BUDGET, EVALUATIONS, HELD_LOCATIONS, event_metrics, partition

optuna.logging.set_verbosity(optuna.logging.WARNING)
OPTUNA_TRIALS = {"catboost": 40, "lightgbm": 30}
OPTUNA_TIMEOUT = {"catboost": 2100, "lightgbm": 1200}
TOP_K = 5
DEVELOPMENT = ["train", "calibration", "selection", "threshold"]


def make_catboost(params):
    from catboost import CatBoostClassifier
    kwargs = {**params}
    kwargs.setdefault("iterations", 900)
    return CatBoostClassifier(early_stopping_rounds=150, thread_count=4, random_seed=314,
                              verbose=False, allow_writing_files=False, **kwargs)


def make_lightgbm(params):
    import lightgbm as lgb
    return lgb.LGBMClassifier(n_estimators=1200, n_jobs=4, random_state=314, verbosity=-1,
                              deterministic=True, force_col_wise=True, **params)


def budget_values(y, p):
    """Budget-feasible recall on validation, or None if infeasible."""
    try:
        point = recall_budget_threshold(threshold_table(y, p), BUDGET)
    except ValueError:
        return None
    return point


def objective_value(y, p):
    ap = float(average_precision_score(y, p)) if len(np.unique(y)) == 2 else 0.0
    point = budget_values(y, p)
    if point is None:
        return -1.0 + 1e-6 * ap
    recall, f2 = float(point["recall"]), float(point["f2"])
    return recall + 1e-3 * ap + 1e-4 * f2


def fit_model(family, params, train, calibration, names):
    X, y = train[names], train.flood_within_24h.astype(int)
    model = make_catboost(params) if family == "catboost" else make_lightgbm(params)
    model.fit(X, y, eval_set=(calibration[names], calibration.flood_within_24h.astype(int)),
              **({"callbacks": [__import__("lightgbm").early_stopping(100, verbose=False)]} if family == "lightgbm" else {}))
    return model


def predict_all(model, parts, names):
    return {s: model.predict_proba(d[names])[:, 1] for s, d in parts.items()}


def run(dataset, out):
    if out.exists():
        raise ValueError("Run exists; use a fresh output directory")
    meta = json.loads((dataset / "dataset_metadata.json").read_text())
    loc = pd.read_csv(dataset / "locations.csv")
    obs = pd.read_parquet(dataset / "weather_observations.parquet")
    labels = pd.read_parquet(dataset / "training_labels.parquet")
    scenarios = pd.read_csv(dataset / "simulation_scenarios.csv", parse_dates=["start", "end"])
    events = pd.read_csv(dataset / "flood_events.csv", parse_dates=["event_start", "event_end"])

    features, extended, weather_only = build_features_v2(obs, loc, meta["config"]["frequency"])
    frame = features.merge(labels, on=["location_id", "timestamp"], validate="one_to_one")
    frame["stage"], reserved = partition(frame, scenarios)
    stages = DEVELOPMENT + EVALUATIONS
    parts = {s: frame[frame.stage.eq(s)].copy() for s in stages}
    for s in DEVELOPMENT:
        if parts[s].flood_within_24h.nunique() != 2:
            raise ValueError(f"Insufficient classes in {s}")

    out.mkdir(parents=True)
    features.to_parquet(out / "features.parquet", index=False)
    frame[["location_id", "timestamp", "stage", "flood_within_24h", "flood_occurred", "forecast_eligible"]].to_parquet(
        out / "splits.parquet", index=False)
    frame.groupby("stage").agg(rows=("stage", "size"), positives=("flood_within_24h", "sum")).to_csv(out / "partition_summary.csv")
    write_json(out / "protocol.json", {"source_type": "synthetic", "notice": NOTICE, "dataset": str(dataset.resolve()),
        "dataset_metadata_sha256": sha256(dataset / "dataset_metadata.json"), "extended_features": extended,
        "weather_only_features": weather_only, "held_location_ids": HELD_LOCATIONS, "reserved_storms": reserved,
        "false_alerts_per_detection_budget": BUDGET, "optuna_trials": OPTUNA_TRIALS, "optuna_timeout_seconds": OPTUNA_TIMEOUT,
        "objective": "Budget-feasible calibration recall, then AP, then F2; infeasible trials score below feasible ones",
        "selection": "Top-5 calibration configs per family, re-evaluated on selection with fresh budget thresholds; winner by selection recall under budget, then AP, F1, Brier",
        "calibration": "none vs sigmoid vs isotonic fit on 2023 H1, compared on 2023 H2 by ECE(10) then Brier",
        "promotion": "See docs/SYNTHETIC_V2_PROTOCOL.md pre-registered criteria", "seed": 314})

    results = {}
    trials_frame = {}

    def load_family(family):
        storage = {}
        def objective(trial):
            if family == "catboost":
                params = {"depth": trial.suggest_int("depth", 4, 8), "learning_rate": trial.suggest_float("learning_rate", .015, .12, log=True),
                          "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1., 20., log=True), "iterations": 900,
                          "random_strength": trial.suggest_float("random_strength", 0., 2.),
                          "bagging_temperature": trial.suggest_float("bagging_temperature", 0., 1.),
                          "border_count": trial.suggest_categorical("border_count", [64, 128, 254]),
                          "auto_class_weights": trial.suggest_categorical("auto_class_weights", ["Balanced", None])}
            else:
                params = {"num_leaves": trial.suggest_int("num_leaves", 8, 64), "max_depth": trial.suggest_int("max_depth", 3, 10),
                          "learning_rate": trial.suggest_float("learning_rate", .015, .12, log=True),
                          "min_child_samples": trial.suggest_int("min_child_samples", 10, 80),
                          "subsample": trial.suggest_float("subsample", .6, 1.), "subsample_freq": 1,
                          "colsample_bytree": trial.suggest_float("colsample_bytree", .6, 1.),
                          "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 20., log=True),
                          "class_weight": trial.suggest_categorical("class_weight", ["balanced", None])}
            model = fit_model(family, params, parts["train"], parts["calibration"], extended)
            p_cal = model.predict_proba(parts["calibration"][extended])[:, 1]
            value = objective_value(parts["calibration"].flood_within_24h, p_cal)
            storage[trial.number] = {"params": params, "objective": value}
            del model
            return value
        sampler = optuna.samplers.TPESampler(seed=314)
        study = optuna.create_study(direction="maximize", sampler=sampler)
        study.optimize(objective, n_trials=OPTUNA_TRIALS[family], timeout=OPTUNA_TIMEOUT[family], n_jobs=1, gc_after_trial=True)
        rows = [{"trial": t.number, "value": t.value, **t.params, "state": str(t.state)} for t in study.trials]
        pd.DataFrame(rows).to_csv(out / f"optuna_trials_{family}.csv", index=False)
        ranked = sorted(storage.values(), key=lambda r: r["objective"], reverse=True)[:TOP_K]
        print(f"{family}: {len(study.trials)} trials, best value {study.best_value:.4f}", flush=True)
        refitted = []
        for entry in ranked:
            entry["model"] = fit_model(family, entry["params"], parts["train"], parts["calibration"], extended)
            refitted.append(entry)
        return refitted

    family_top = {f: load_family(f) for f in ["catboost", "lightgbm"]}

    candidates = {}
    fitted = {}
    for family, top in family_top.items():
        for rank, entry in enumerate(top):
            name = f"{family}_tuned{rank+1}"
            candidates[name] = {"family": family, "params": entry["params"], "features": extended,
                                "model": entry["model"], "calibration": "none", "rank": rank}
    baselines = {
        "logistic_baseline": LogisticRegression(C=1., class_weight="balanced", max_iter=1500, random_state=314),
        "random_forest_baseline": RandomForestClassifier(n_estimators=160, max_depth=14, min_samples_leaf=10,
                                                         class_weight="balanced_subsample", n_jobs=4, random_state=314),
    }
    for name, estimator in baselines.items():
        model = Pipeline([("imputer", SimpleImputer(strategy="median", add_indicator=True)),
                          ("scale", StandardScaler()), ("classifier", estimator)])
        model.fit(parts["train"][extended], parts["train"].flood_within_24h.astype(int))
        candidates[name] = {"family": "sklearn", "params": {}, "features": extended, "model": model, "calibration": "none", "rank": 0}

    # Weather-only comparison for the best tuned CatBoost and LightGBM configs.
    for name, source in [("catboost_weather_only", "catboost_tuned1"), ("lightgbm_weather_only", "lightgbm_tuned1")]:
        family = candidates[source]["family"]
        model = fit_model(family, {**candidates[source]["params"]}, parts["train"], parts["calibration"], weather_only)
        candidates[name] = {"family": family, "params": candidates[source]["params"], "features": weather_only,
                            "model": model, "calibration": "none", "rank": 0, "weather_only": True}

    print("Evaluating candidates on selection", flush=True)
    for name, entry in candidates.items():
        entry["probabilities"] = predict_all(entry["model"], parts, entry["features"])

    selection_rows = []
    for name, entry in candidates.items():
        d, p = parts["selection"], entry["probabilities"]["selection"]
        point = budget_values(d.flood_within_24h, p)
        row = {"candidate": name, "family": entry["family"], "weather_only": entry.get("weather_only", False),
               "feasible": point is not None, "threshold": float(point["threshold"]) if point else float(np.nextafter(1., 2.))}
        row.update(score(d.flood_within_24h, p, row["threshold"]))
        row["accuracy"] = float(accuracy_score(d.flood_within_24h, p >= row["threshold"]))
        row["balanced_accuracy"] = float(balanced_accuracy_score(d.flood_within_24h, p >= row["threshold"]))
        selection_rows.append(row)
    selection = pd.DataFrame(selection_rows)
    selection.to_csv(out / "selection_metrics.csv", index=False)
    feasible = selection[selection.feasible].sort_values(
        ["recall", "pr_auc_average_precision", "f1", "brier", "candidate"], ascending=[False, False, False, True, True])
    if feasible.empty:
        raise ValueError("No candidate meets the validation false-alert budget")
    winner = feasible.iloc[0].candidate
    write_json(out / "selection_lock.json", {"selected": winner, "dataset_sha256": sha256(dataset / "dataset_metadata.json"),
        "selection_table_sha256": sha256(out / "selection_metrics.csv")})
    print("Selected on selection partition:", winner, flush=True)

    # Calibration-method comparison for the winner: fit on calibration, compare on selection.
    entry = candidates[winner]
    raw_cal = entry["probabilities"]["calibration"]
    y_cal = parts["calibration"].flood_within_24h
    calibrators = {"none": None, "sigmoid": fit_sigmoid(raw_cal, y_cal),
                   "isotonic": IsotonicRegression(out_of_bounds="clip").fit(raw_cal, y_cal)}
    cal_rows = []
    for method, calibrator in calibrators.items():
        probs = {}
        for stage in stages:
            raw = entry["probabilities"][stage]
            probs[stage] = raw if calibrator is None else (
                apply_sigmoid(calibrator, raw) if method == "sigmoid" else calibrator.predict(raw))
        point = budget_values(parts["selection"].flood_within_24h, probs["selection"])
        row = {"method": method, "feasible": point is not None,
               "threshold": float(point["threshold"]) if point else float(np.nextafter(1., 2.))}
        row.update(score(parts["selection"].flood_within_24h, probs["selection"], row["threshold"]))
        cal_rows.append(row)
        entry.setdefault("method_probabilities", {})[method] = probs
    calibration_table = pd.DataFrame(cal_rows)
    calibration_table.to_csv(out / "calibration_comparison.csv", index=False)
    valid = calibration_table[calibration_table.feasible].sort_values(["ece_equal_width_10_bins", "brier", "method"])
    method = valid.iloc[0].method if not valid.empty else "none"
    entry["calibration"] = method
    entry["probabilities"] = entry["method_probabilities"][method]
    print("Calibration method chosen on selection:", method, flush=True)

    # Operating thresholds come from the 2024 H1 threshold partition only (protocol).
    operating_thresholds = {}
    for name, e in candidates.items():
        point = budget_values(parts["threshold"].flood_within_24h, e["probabilities"]["threshold"])
        operating_thresholds[name] = {"threshold": float(point["threshold"]) if point else float(np.nextafter(1., 2.)),
                                      "feasible": point is not None}
    write_json(out / "thresholds.json", operating_thresholds)

    all_metrics, per_location, saved = [], [], []
    for name, e in candidates.items():
        threshold = operating_thresholds[name]["threshold"]
        for stage in stages:
            p = e["probabilities"][stage]
            row = {"candidate": name, "stage": stage, "threshold": threshold, **score(parts[stage].flood_within_24h, p, threshold),
                   **event_metrics(parts[stage], p, threshold, events)}
            if parts[stage].flood_within_24h.nunique() == 2:
                pred = p >= threshold
                row["accuracy"] = float(accuracy_score(parts[stage].flood_within_24h, pred))
                row["balanced_accuracy"] = float(balanced_accuracy_score(parts[stage].flood_within_24h, pred))
                row["roc_auc"] = float(roc_auc_score(parts[stage].flood_within_24h, p))
            all_metrics.append(row)
            if stage in EVALUATIONS:
                for location_id, g in parts[stage].groupby("location_id"):
                    mask = parts[stage].location_id.eq(location_id).to_numpy()
                    per_location.append({"candidate": name, "stage": stage, "location_id": location_id,
                                         **score(g.flood_within_24h, p[mask], threshold),
                                         **event_metrics(g, p[mask], threshold, events)})
            saved.append(parts[stage][["location_id", "timestamp", "flood_within_24h"]].assign(
                candidate=name, stage=stage, probability=p, threshold=threshold))
    pd.DataFrame(all_metrics).to_csv(out / "metrics.csv", index=False)
    pd.DataFrame(per_location).to_csv(out / "per_location_metrics.csv", index=False)
    pd.concat(saved, ignore_index=True).to_parquet(out / "predictions.parquet", index=False)

    # Feature importance of the tuned winner.
    estimator = entry["model"]
    if isinstance(estimator, Pipeline):
        estimator = estimator.named_steps["classifier"]
    importance = getattr(estimator, "feature_importances_", None)
    if importance is None and hasattr(estimator, "coef_"):
        importance = np.abs(estimator.coef_[0])
    if importance is not None:
        pd.DataFrame({"feature": entry["features"], "importance": importance}).sort_values(
            "importance", ascending=False).to_csv(out / "feature_importance.csv", index=False)

    contest = {name: {"candidate": name, "family": e["family"], "params": e["params"], "features": e["features"],
                      "calibration": e.get("calibration", "none"), "weather_only": e.get("weather_only", False)}
               for name, e in candidates.items()}
    write_json(out / "best_params.json", contest)

    results.update({"winner": winner, "method": method, "threshold": operating_thresholds[winner]["threshold"]})
    save_winner_bundle(dataset, out, winner, entry, method, operating_thresholds[winner]["threshold"], extended, weather_only)
    plot_results(out, parts, {n: e["probabilities"] for n, e in candidates.items()},
                 {n: operating_thresholds[n]["threshold"] for n in candidates}, winner)
    promotion = promotion_decision(dataset, out, winner, entry, parts, selection, operating_thresholds)
    write_json(out / "promotion_decision.json", promotion)
    print(json.dumps(promotion, indent=2), flush=True)
    for stage in ["test", "held_location", "storm_holdout", "held_location_storm"]:
        row = pd.DataFrame(all_metrics).query("candidate == @winner and stage == @stage").iloc[0]
        print(f"[diagnostic {stage}] recall={row.recall:.4f} precision={row.precision:.4f} "
              f"ap={row.pr_auc_average_precision:.4f} event_recall={row.event_recall}", flush=True)
    return results


def save_winner_bundle(dataset, out, winner, entry, method, threshold, extended, weather_only):
    import joblib
    names = entry["features"]
    names = extended if names == "extended" else weather_only if names == "weather_only" else names
    bundle = {"model": entry["model"], "calibrator": None, "features": names, "threshold": float(threshold),
              "model_version": f"synthetic-fiji-v2-{winner}__{method}", "source_type": "synthetic"}
    model_path = out / "candidate_model.joblib"
    joblib.dump(bundle, model_path)
    labels = pd.read_parquet(Path(dataset) / "training_labels.parquet", columns=["location_id", "timestamp", "flood_occurred"])
    labels.to_parquet(out / "simulation_outcomes.parquet", index=False)
    write_json(out / "candidate_metadata.json", {"model_version": bundle["model_version"], "selected_candidate": winner,
        "calibration": method, "threshold": float(threshold), "source_type": "synthetic", "notice": NOTICE,
        "features": names, "n_features": len(names), "model_sha256": sha256(model_path),
        "note": "Candidate only; package with ml.synthetic.finalize_v2 before serving."})


def promotion_decision(dataset, out, winner, entry, parts, selection, operating_thresholds):
    row = selection[selection.candidate.eq(winner)].iloc[0]
    v1 = {"selection_recall": 0.8824074074074074, "selection_ap": 0.7413878083197479,
          "test_ap": 0.283944, "test_event_recall": 0.877551}
    # Selection-period diagnostic values (validation only) for the pre-registered rule.
    criteria = {
        "feasible_on_selection": bool(row.feasible),
        "selection_recall_beats_v1": bool(row.recall > v1["selection_recall"]),
        "selection_ap_at_least_v1": bool(row.pr_auc_average_precision >= v1["selection_ap"]),
    }
    decision = {"winner": winner, "v1_reference": v1, "operating_threshold": operating_thresholds[winner]["threshold"],
                "selection_recall": float(row.recall), "selection_ap": float(row.pr_auc_average_precision),
                "criteria": criteria,
                "preliminary_candidate": bool(all(criteria.values())),
                "note": "Test/held/storm/reserved diagnostics do not select; severe diagnostic collapse vetoes per protocol."}
    write_json(out / "promotion_decision.json", decision)
    return decision


def plot_results(out, parts, probabilities, thresholds, winner):
    bins = []
    figure_stages = ["selection", "threshold"] + EVALUATIONS
    for stage in figure_stages:
        d = parts[stage]
        fig, axes = plt.subplots(1, 2, figsize=(13, 5))
        for candidate, probs in probabilities.items():
            p = probs[stage]
            if d.flood_within_24h.sum() and d.flood_within_24h.nunique() == 2:
                precision, recall, _ = precision_recall_curve(d.flood_within_24h, p)
                axes[0].plot(recall, precision, label=candidate, alpha=.7)
            for r in reliability(d.flood_within_24h, p):
                bins.append({"candidate": candidate, "stage": stage, **r})
        axes[0].set(xlabel="Recall", ylabel="Precision", title=stage + " — simulator outcomes")
        axes[0].legend(fontsize=5)
        for candidate, probs in list(probabilities.items())[:6]:
            rel = reliability(d.flood_within_24h, probs[stage])
            axes[1].plot([r["mean_probability"] for r in rel], [r["positive_fraction"] for r in rel], marker=".", label=candidate)
        axes[1].plot([0, 1], [0, 1], "k--")
        axes[1].set(xlabel="Predicted probability", ylabel="Simulated incidence", title="Calibration")
        fig.tight_layout()
        fig.savefig(out / (stage + "_pr_calibration.png"), dpi=160)
        plt.close(fig)
    pd.DataFrame(bins).to_csv(out / "calibration_bins.csv", index=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("ml/data/synthetic_fiji/v1"))
    parser.add_argument("--out", type=Path, default=Path("ml/runs/synthetic-v2"))
    args = parser.parse_args()
    train_started = time.monotonic()
    result = run(args.dataset, args.out)
    write_json(args.out / "run_summary.json", {**result, "total_seconds": time.monotonic() - train_started})
