"""Publish a per-scenario Synthetic V3 research bundle for the research-only selector.

Verifies the run's saved candidate bundle reproduces the run's own predictions,
enforces the anti-leakage policy (no truth/label columns in the feature list),
and writes a self-contained research bundle directory consumed by the backend
research routes. Never touches the deployed V1 serving directory.

Usage:
    backend/.venv/bin/python -m ml.synthetic.finalize_v3 \
        --dataset ml/data/synthetic_fiji/v3/realistic \
        --run ml/runs/synthetic-v3/realistic
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ml.refinement import sha256
from ml.synthetic.features_v2 import RAW_COLUMNS
from ml.synthetic.generate import NOTICE
from ml.train import write_json
from ml.training03 import apply_sigmoid

TRUTH_COLUMNS = {"flood_occurred", "flood_within_24h", "flood_within_48h",
                 "flood_within_72h", "forecast_eligible", "event_id", "scenario_id", "stage"}
METADATA_FILES = ("dataset_metadata.json",)


def _verify_bundle(run, features):
    meta = json.loads((run / "candidate_metadata.json").read_text())
    model_path = run / "candidate_model.joblib"
    if sha256(model_path) != meta["model_sha256"]:
        raise ValueError("Candidate bundle checksum does not match candidate_metadata.json")
    bundle = joblib.load(model_path)
    if bundle.get("source_type") != "synthetic":
        raise ValueError("Candidate bundle is not marked synthetic")
    names = bundle["features"]
    leaked = sorted(set(names) & TRUTH_COLUMNS)
    if leaked:
        raise ValueError(f"Feature list contains truth/label columns: {leaked}")
    missing = sorted(set(names) - set(features.columns))
    if missing:
        raise ValueError(f"Feature list references missing columns: {missing}")
    return bundle, meta


def _verify_reproduces(run, bundle, features, splits):
    predictions = pd.read_parquet(run / "predictions.parquet")
    winner = json.loads((run / "selection_lock.json").read_text())["selected"]
    row = predictions[(predictions.candidate == winner) & (predictions.stage == "test")].sort_values(
        ["location_id", "timestamp"]).reset_index(drop=True)
    keys = splits[splits.stage.eq("test")][["location_id", "timestamp"]]
    frame = features.merge(keys, on=["location_id", "timestamp"], validate="one_to_one").sort_values(
        ["location_id", "timestamp"]).reset_index(drop=True)
    if len(row) != len(frame):
        raise ValueError("Test predictions and splits disagree on row count")
    raw = bundle["model"].predict_proba(frame[bundle["features"]])[:, 1]
    if bundle["calibrator"] is not None:
        if bundle.get("calibration") == "sigmoid":
            raw = apply_sigmoid(bundle["calibrator"], raw)
        else:
            raw = bundle["calibrator"].predict(raw)
    if not np.allclose(raw, row.probability.to_numpy(), atol=1e-10):
        raise ValueError("Bundle does not reproduce the run's test predictions")
    return int(len(row))


def build_truth(labels, events, splits):
    truth = labels[["location_id", "timestamp", "flood_occurred", "flood_within_24h"]].copy()
    truth = truth.merge(splits[["location_id", "timestamp", "stage"]],
                        on=["location_id", "timestamp"], validate="one_to_one")
    truth["event_id"] = None
    truth["scenario_id"] = None
    for event in events.itertuples():
        mask = truth.location_id.eq(event.location_id) & \
            truth.timestamp.between(event.event_start, event.event_end)
        truth.loc[mask, "event_id"] = event.event_id
        truth.loc[mask, "scenario_id"] = event.scenario_id
    return truth


def package(dataset, run, out):
    dataset, run = Path(dataset), Path(run)
    out = Path(out)
    if out.exists():
        raise ValueError("Bundle exists; use --force to overwrite")
    features = pd.read_parquet(run / "features.parquet")
    splits = pd.read_parquet(run / "splits.parquet")
    labels = pd.read_parquet(dataset / "training_labels.parquet",
                             columns=["location_id", "timestamp", "flood_occurred", "flood_within_24h"])
    events = pd.read_csv(dataset / "flood_events.csv", parse_dates=["event_start", "event_end"])
    locations = pd.read_csv(dataset / "locations.csv")
    scenarios = pd.read_csv(dataset / "simulation_scenarios.csv", parse_dates=["start", "end"])
    dataset_meta = json.loads((dataset / "dataset_metadata.json").read_text())
    protocol = json.loads((run / "protocol.json").read_text())
    summary = json.loads((run / "run_summary.json").read_text())
    lock = json.loads((run / "selection_lock.json").read_text())

    bundle, meta = _verify_bundle(run, features)
    n_rows = _verify_reproduces(run, bundle, features, splits)
    if sorted(locations.location_id) != sorted(features.location_id.unique()):
        raise ValueError("Location ids do not match the registry")
    scenario = meta["scenario"]
    if scenario != dataset_meta["config"]["scenario"]:
        raise ValueError("Bundle scenario does not match the dataset scenario")

    weather_frame = features.copy()
    truth = build_truth(labels, events, splits)
    events_out = events.merge(locations[["location_id", "slug", "name"]],
                              on="location_id", validate="many_to_one")

    out.mkdir(parents=True)
    model_path = out / "research_model.joblib"
    joblib.dump(bundle, model_path)
    weather_frame.to_parquet(out / "research_features.parquet", index=False)
    truth.to_parquet(out / "research_truth.parquet", index=False)
    events_out.to_csv(out / "research_events.csv", index=False)
    locations.to_csv(out / "research_locations.csv", index=False)

    partition_dates = {stage: {"min": str(row["min"]), "max": str(row["max"])}
                       for stage, row in splits.groupby("stage").timestamp.agg(
                           ["min", "max"]).to_dict("index").items()}
    bootstrap = json.loads((run / "bootstrap_intervals.json").read_text())
    selection = pd.read_csv(run / "selection_metrics.csv")
    write_json(out / "research_scenario.json", {
        "source_type": "synthetic", "notice": NOTICE, "research_only": True,
        "scenario": scenario, "dataset_version": dataset_meta["dataset_version"],
        "dataset": str(dataset.resolve()), "run": str(run.resolve()),
        "dataset_metadata_sha256": sha256(dataset / "dataset_metadata.json"),
        "selection_lock_sha256": sha256(run / "selection_lock.json"),
        "model_version": bundle["model_version"], "selected_candidate": lock["selected"],
        "calibration": meta["calibration"], "threshold": meta["threshold"], "n_features": meta["n_features"],
        "model_sha256": sha256(model_path), "reproduced_test_rows": n_rows,
        "time_range": {"start": str(weather_frame.timestamp.min()), "end": str(weather_frame.timestamp.max())},
        "observations": int(len(weather_frame)), "locations": int(len(locations)),
        "weather_columns": list(RAW_COLUMNS),
        "events": {"total": int(len(events)), "by_severity": events.severity.value_counts().to_dict(),
                   "cyclone_like": int(events.scenario_id.isin(
                       scenarios[scenarios.cyclone_like].scenario_id).sum())},
        "partitions": partition_dates, "held_location_ids": protocol["held_location_ids"],
        "reserved_storms": protocol["reserved_storms"],
        "false_alerts_per_detection_budget": protocol["false_alerts_per_detection_budget"],
        "inner_folds": protocol["inner_folds"], "seed": protocol["seed"],
        "protocol_document": protocol["protocol_document"],
        "bootstrap_intervals": bootstrap,
        "selection_top": selection.sort_values(
            ["feasible", "recall", "pr_auc_average_precision"], ascending=[False, False, False]
        ).head(5)[["candidate", "feasible", "recall", "pr_auc_average_precision", "f2",
                   "brier", "ece_equal_width_10_bins"]].to_dict("records"),
        "risk_tiers": "Provisional research bands relative to the validation threshold: "
                      "LOW <0.5t, MODERATE <t, HIGH <min(1,1.5t), VERY_HIGH otherwise",
        "ground_truth_policy": "Ground truth (flood_occurred, flood_within_24h, event_id) is served "
                               "from a separate file for display only and is never a model input.",
        "packaged_at": datetime.now(timezone.utc).isoformat()})
    manifest = {p.name: sha256(p) for p in sorted(out.iterdir()) if p.is_file()}
    write_json(out / "research_manifest.json", {"source_type": "synthetic", "scenario": scenario,
                                                "model_version": bundle["model_version"], "hashes": manifest})
    return {"scenario": scenario, "model_version": bundle["model_version"], "out": str(out),
            "files": sorted(manifest)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.force and args.out.exists():
        import shutil
        shutil.rmtree(args.out)
    print(json.dumps(package(args.dataset, args.run, args.out), indent=2))
