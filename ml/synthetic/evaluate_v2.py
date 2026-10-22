"""Reserved independent evaluation, v1 comparison, promotion decision, optional publish.

Runs only after the winner and threshold are frozen in ml/runs/synthetic-v2.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve

from ml.refinement import reliability, score, sha256
from ml.train import write_json
from ml.training03 import apply_sigmoid
from ml.synthetic.features_v2 import build_features_v2
from ml.synthetic.generate import NOTICE
from ml.synthetic.train import event_metrics

RESERVED = {"reserved_seed_default": "ml/data/synthetic_fiji/v2-reserved-a",
            "reserved_seed_wetter": "ml/data/synthetic_fiji/v2-reserved-b"}
HELD_LOCATIONS = [3, 10, 12]


def apply_probabilities(bundle, raw):
    if bundle["calibrator"] is None:
        return raw
    metadata = bundle.get("calibration")
    if metadata == "isotonic":
        return bundle["calibrator"].predict(raw)
    return apply_sigmoid(bundle["calibrator"], raw)


def evaluate_reserved(bundle, directory):
    directory = Path(directory)
    meta = json.loads((directory / "dataset_metadata.json").read_text())
    loc = pd.read_csv(directory / "locations.csv")
    obs = pd.read_parquet(directory / "weather_observations.parquet")
    labels = pd.read_parquet(directory / "training_labels.parquet")
    events = pd.read_csv(directory / "flood_events.csv", parse_dates=["event_start", "event_end"])
    features, extended, weather_only = build_features_v2(obs, loc, meta["config"]["frequency"])
    frame = features.merge(labels, on=["location_id", "timestamp"], validate="one_to_one")
    frame = frame[frame.history_ready & frame.forecast_eligible]
    names = bundle["features"]
    raw = bundle["model"].predict_proba(frame[names])[:, 1]
    probability = apply_probabilities(bundle, raw)
    rows, per_location = [], []
    for subset, mask in [("all", pd.Series(True, index=frame.index)), ("unseen_locations", frame.location_id.isin(HELD_LOCATIONS))]:
        subset_frame = frame[mask]
        subset_probability = probability[mask.to_numpy()]
        rows.append({"model": "v2_candidate", "subset": subset, **score(subset_frame.flood_within_24h, subset_probability, bundle["threshold"]),
                     **event_metrics(subset_frame, subset_probability, bundle["threshold"], events)})
        for location_id, g in subset_frame.groupby("location_id"):
            local = location_id == subset_frame.location_id
            p = subset_probability[local.to_numpy()]
            per_location.append({"subset": subset, "location_id": location_id, "rows": len(g), "positives": int(g.flood_within_24h.sum()),
                                 **score(g.flood_within_24h, p, bundle["threshold"]),
                                 **event_metrics(g, p, bundle["threshold"], events)})
    return pd.DataFrame(rows), pd.DataFrame(per_location)


def v1_reference():
    metrics = pd.read_csv("ml/runs/synthetic-v1/metrics.csv")
    selection = pd.read_csv("ml/runs/synthetic-v1/selection_metrics.csv")
    meta = json.loads(Path("ml/runs/synthetic-v1/model_metadata.json").read_text())
    candidate = meta["selected_candidate"]
    test = metrics[(metrics.candidate == candidate) & (metrics.stage == "test")].iloc[0]
    select = selection[selection.candidate == candidate].iloc[0]
    return {"candidate": candidate, "threshold": meta["threshold"],
            "test": {"recall": float(test.recall), "precision": float(test.precision), "f1": float(test.f1),
                     "ap": float(test.pr_auc_average_precision), "roc_auc": float(test.roc_auc), "brier": float(test.brier),
                     "event_recall": float(test.event_recall)},
            "selection": {"recall": float(select.recall), "ap": float(select.pr_auc_average_precision),
                          "note": "v1 selection_metrics (selection-derived budget threshold); AP is threshold-independent and matches protocol 0.74139"}}


def serving_check(run, dataset):
    run, dataset = Path(run), Path(dataset)
    bundle = joblib.load(run / "selected_model.joblib")
    meta = json.loads((dataset / "dataset_metadata.json").read_text())
    loc = pd.read_csv(dataset / "locations.csv")
    obs = pd.read_parquet(dataset / "weather_observations.parquet")
    full, _, _ = build_features_v2(obs, loc, meta["config"]["frequency"])
    sample = obs.sample(5000, random_state=314)
    start = sample.timestamp.min()
    window = obs[obs.timestamp >= start - pd.Timedelta(days=14)]
    partial, _, _ = build_features_v2(window, loc, meta["config"]["frequency"])
    left = sample.merge(partial, on=["location_id", "timestamp"], suffixes=("_x", ""))
    right = sample.merge(full, on=["location_id", "timestamp"], suffixes=("_x", ""))
    warm = left.groupby("location_id").cumcount() >= 0
    columns = bundle["features"]
    max_diff = float(np.nanmax(np.abs(left.loc[warm, columns].to_numpy(dtype="float64") - right.loc[warm, columns].to_numpy(dtype="float64"))))
    sys.path.insert(0, str(Path("backend").resolve()))
    from app.services.synthetic_inference import SyntheticModel
    model = SyntheticModel(run)
    probe = full[full.history_ready].iloc[0]
    prediction = model.predict(int(probe.location_id), probe.timestamp)
    return {"windowed_feature_max_abs_diff": max_diff,
            "serving_model_loads": model.metadata["source_type"] == "synthetic",
            "serving_prediction_status": prediction["status"], "serving_model_version": model.metadata["model_version"],
            "serving_features": len(model.features.columns)}


def publish(run, dataset, target):
    run, dataset, target = Path(run), Path(dataset), Path(target)
    if target.exists():
        raise ValueError("Publishing target already exists; refusing to overwrite a preserved bundle")
    target.mkdir(parents=True)
    shutil.copy2(run / "selected_model.joblib", target / "selected_model.joblib")
    shutil.copy2(run / "model_metadata.json", target / "model_metadata.json")
    shutil.copy2(run / "features.parquet", target / "features.parquet")
    labels = pd.read_parquet(Path(dataset) / "training_labels.parquet", columns=["location_id", "timestamp", "flood_occurred"])
    labels.to_parquet(target / "simulation_outcomes.parquet", index=False)
    write_json(target / "bundle_manifest.json", {p.name: sha256(p) for p in target.iterdir() if p.is_file()})


def evaluate_v1_reserved(directory):
    """Evaluate the preserved v1 serving bundle on the reserved datasets for a like-for-like comparison."""
    from ml.synthetic.features import build_features
    bundle = joblib.load("ml/artifacts/synthetic/v1/selected_model.joblib")
    directory = Path(directory)
    meta = json.loads((directory / "dataset_metadata.json").read_text())
    loc = pd.read_csv(directory / "locations.csv")
    obs = pd.read_parquet(directory / "weather_observations.parquet")
    labels = pd.read_parquet(directory / "training_labels.parquet")
    events = pd.read_csv(directory / "flood_events.csv", parse_dates=["event_start", "event_end"])
    features, names = build_features(obs, loc, meta["config"]["frequency"])
    frame = features.merge(labels, on=["location_id", "timestamp"], validate="one_to_one")
    frame = frame[frame.history_ready & frame.forecast_eligible]
    raw = bundle["model"].predict_proba(frame[names])[:, 1]
    probability = raw if bundle.get("calibrator") is None else apply_sigmoid(bundle["calibrator"], raw)
    rows = []
    for subset, mask in [("all", pd.Series(True, index=frame.index)), ("unseen_locations", frame.location_id.isin(HELD_LOCATIONS))]:
        subset_frame = frame[mask]
        subset_probability = probability[mask.to_numpy()]
        rows.append({"model": "v1_catboost", "subset": subset,
                     **score(subset_frame.flood_within_24h, subset_probability, bundle["threshold"]),
                     **event_metrics(subset_frame, subset_probability, bundle["threshold"], events)})
    return pd.DataFrame(rows)


def run(run_dir, skip_reserved=False):
    run_dir = Path(run_dir)
    metadata = json.loads((run_dir / "model_metadata.json").read_text())
    bundle = joblib.load(run_dir / "selected_model.joblib")
    bundle["calibration"] = metadata["calibration"]
    v1 = v1_reference()
    reserved_tables, reserved_locations = [], []
    if not skip_reserved:
        for name, directory in RESERVED.items():
            table, per_location = evaluate_reserved(bundle, directory)
            table.insert(0, "evaluation", name)
            per_location.insert(0, "evaluation", name)
            reserved_tables.append(table)
            reserved_locations.append(per_location)
            v1_table = evaluate_v1_reserved(directory)
            v1_table.insert(0, "evaluation", name)
            reserved_tables.append(v1_table)
    reserved = pd.concat(reserved_tables, ignore_index=True) if reserved_tables else pd.DataFrame()
    reserved_locations = pd.concat(reserved_locations, ignore_index=True) if reserved_locations else pd.DataFrame()
    if not reserved.empty:
        reserved.to_csv(run_dir / "reserved_evaluation.csv", index=False)
        reserved_locations.to_csv(run_dir / "reserved_per_location.csv", index=False)

    metrics = pd.read_csv(run_dir / "metrics.csv")
    winner = metadata["selected_candidate"]
    diagnostic = metrics[metrics.candidate.eq(winner)]
    diagnostic.to_csv(run_dir / "diagnostic_metrics.csv", index=False)
    confusion_rows = []
    for row in metrics.itertuples():
        values = getattr(row, "confusion_matrix_tn_fp_fn_tp", None)
        if isinstance(values, str):
            tn, fp, fn, tp = (int(v) for v in values.strip("[]").split(","))
            confusion_rows.append({"candidate": row.candidate, "stage": row.stage, "TN": tn, "FP": fp, "FN": fn, "TP": tp})
    pd.DataFrame(confusion_rows).to_csv(run_dir / "confusion_matrices.csv", index=False)

    check = serving_check(run_dir, "ml/data/synthetic_fiji/v1")
    write_json(run_dir / "serving_compatibility.json", check)

    selection = pd.read_csv(run_dir / "selection_metrics.csv")
    selection_row = selection[selection.candidate.eq(winner)].iloc[0]
    v1_test = v1["test"]
    v2_test = diagnostic[diagnostic.stage.eq("test")].iloc[0]
    reserved_all = reserved[(reserved.subset.eq("all")) & (reserved.model.eq("v2_candidate"))].set_index("evaluation") if not reserved.empty else None
    criteria = {
        "selection_feasible": bool(selection_row.feasible),
        "selection_recall_beats_v1": bool(selection_row.recall > v1["selection"]["recall"]),
        "selection_ap_at_least_v1": bool(selection_row.pr_auc_average_precision >= v1["selection"]["ap"]),
        "diagnostic_test_ap_floor_0.25": bool(v2_test.pr_auc_average_precision >= 0.25),
        "diagnostic_test_event_recall_floor_0.80": bool(v2_test.event_recall >= 0.80),
    }
    if not reserved.empty:
        a = reserved_all.loc["reserved_seed_default"]
        criteria["reserved_default_ap_floor_0.15"] = bool(a.pr_auc_average_precision >= 0.15)
        criteria["reserved_default_event_recall_floor_0.50"] = bool(a.event_recall >= 0.50)
    promoted = all(criteria.values())
    decision = {"model_version": metadata["model_version"], "promoted": promoted, "criteria": criteria,
                "selection": {"recall": float(selection_row.recall), "ap": float(selection_row.pr_auc_average_precision),
                              "threshold": float(metadata["threshold"])},
                "v1_selection": v1["selection"], "v2_diagnostic_test": {"recall": float(v2_test.recall), "ap": float(v2_test.pr_auc_average_precision),
                                                                        "event_recall": float(v2_test.event_recall)},
                "v1_test": v1_test, "serving_check": check}
    write_json(run_dir / "promotion_final.json", decision)
    if promoted:
        publish(run_dir, "ml/data/synthetic_fiji/v1", "ml/artifacts/synthetic/v2")
    comparison = pd.DataFrame([
        {"model": "v1 CatBoost", "partition": "selection", "recall": v1["selection"]["recall"], "ap": v1["selection"]["ap"]},
        {"model": f"v2 {winner}", "partition": "selection", "recall": float(selection_row.recall), "ap": float(selection_row.pr_auc_average_precision)},
        {"model": "v1 CatBoost", "partition": "test (diagnostic)", "recall": v1_test["recall"], "ap": v1_test["ap"]},
        {"model": f"v2 {winner}", "partition": "test (diagnostic)", "recall": float(v2_test.recall), "ap": float(v2_test.pr_auc_average_precision)},
    ])
    if not reserved.empty:
        for evaluation, group in reserved.groupby("evaluation"):
            for subset in ["all", "unseen_locations"]:
                for model in ["v1_catboost", "v2_candidate"]:
                    row = group[(group.model.eq(model)) & (group.subset.eq(subset))]
                    if row.empty:
                        continue
                    row = row.iloc[0]
                    label = "v1 CatBoost" if model == "v1_catboost" else f"v2 {winner}"
                    comparison.loc[len(comparison)] = {"model": label, "partition": f"{evaluation} ({subset})",
                                                       "recall": float(row.recall), "ap": float(row.pr_auc_average_precision),
                                                       "precision": float(row.precision), "f1": float(row.f1),
                                                       "event_recall": float(row.event_recall),
                                                       "false_alerts_per_1000": float(row.false_alerts_per_1000)}
    comparison.to_csv(run_dir / "comparison_vs_v1.csv", index=False)
    print(reserved.to_string(index=False) if not reserved.empty else "no reserved evaluation")
    print(json.dumps(decision, indent=2))
    return decision


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=Path("ml/runs/synthetic-v2"))
    parser.add_argument("--skip-reserved", action="store_true")
    args = parser.parse_args()
    run(args.run, args.skip_reserved)
