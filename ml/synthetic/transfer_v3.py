"""Pre-registered Synthetic V3 extras: fixed baselines and OOD transfer.

1. Baselines (majority prevalence, v1 hydrological rule) scored with the same
   ``evaluate`` metrics as every candidate, per scenario partition.
2. Out-of-distribution transfer: the **realistic** winner's bundle (features,
   calibrator and threshold frozen on realistic validation data only) is applied
   unchanged to the controlled and stress datasets. No re-tuning, no
   re-thresholding, no recalibration on OOD data — exactly the single
   cross-scenario transfer pre-registered in docs/SYNTHETIC_V3_PROTOCOL.md.

Writes ml/runs/synthetic-v3/baselines_v3.json and transfer_v3.json.
"""
import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ml.synthetic.generate import NOTICE
from ml.synthetic.metrics_v3 import evaluate
from ml.train import write_json

SCENARIOS = ("controlled", "realistic", "stress")
STAGES = ["threshold", "test", "held_location", "storm_holdout", "held_location_storm"]
RULE_FEATURES = ("rainfall_mm_total_24h", "soil_moisture_pct")


def load_scenario(run):
    run = Path(run)
    features = pd.read_parquet(run / "features.parquet")
    splits = pd.read_parquet(run / "splits.parquet")
    frame = features.merge(splits[["location_id", "timestamp", "stage", "flood_within_24h"]],
                           on=["location_id", "timestamp"], validate="one_to_one")
    events = pd.read_csv(Path("ml/data/synthetic_fiji/v3") / run.name / "flood_events.csv",
                         parse_dates=["event_start", "event_end"])
    return frame, events


def majority_probability(train_labels):
    return float(train_labels.mean())


def hydrological_rule(frame):
    return ((frame[RULE_FEATURES[0]] > 80) & (frame[RULE_FEATURES[1]] > 75)).astype(float).to_numpy()


def score_partition(data, probability, threshold, events):
    return evaluate(data, probability, threshold, events, include_bootstrap=False)


def baselines(runs_root):
    results = {}
    for scenario in SCENARIOS:
        frame, events = load_scenario(Path(runs_root) / scenario)
        prevalence = majority_probability(frame.loc[frame.stage.eq("train"), "flood_within_24h"])
        per_scenario = {}
        for stage in STAGES:
            data = frame[frame.stage.eq(stage)]
            if data.empty:
                continue
            per_scenario[stage] = {
                "rows": int(len(data)), "positives": int(data.flood_within_24h.sum()),
                "majority_prevalence": prevalence,
                "majority": {k: v for k, v in score_partition(
                    data, np.full(len(data), prevalence), 0.5, events).items() if not isinstance(v, dict)},
                "hydrological_rule": {k: v for k, v in score_partition(
                    data, hydrological_rule(data), 0.5, events).items() if not isinstance(v, dict)},
            }
        results[scenario] = per_scenario
    return {"source_type": "synthetic", "research_only": True, "notice": NOTICE,
            "budget": 75 / 42, "scenarios": results}


def transfer(runs_root, source="realistic"):
    run = Path(runs_root) / source
    bundle = joblib.load(run / "candidate_model.joblib")
    source_meta = json.loads((run / "candidate_metadata.json").read_text())
    results = {}
    for scenario in SCENARIOS:
        if scenario == source:
            continue
        frame, events = load_scenario(Path(runs_root) / scenario)
        per_scenario = {}
        for stage in STAGES:
            data = frame[frame.stage.eq(stage)]
            if data.empty:
                continue
            raw = bundle["model"].predict_proba(data[bundle["features"]])[:, 1]
            if bundle["calibrator"] is not None:
                if bundle.get("calibration") == "sigmoid":
                    clipped = np.clip(raw, 1e-6, 1 - 1e-6)
                    p = bundle["calibrator"].predict_proba(
                        np.log(clipped / (1 - clipped)).reshape(-1, 1))[:, 1]
                else:
                    p = bundle["calibrator"].predict(raw)
            else:
                p = raw
            per_scenario[stage] = {k: v for k, v in score_partition(
                data, p, bundle["threshold"], events).items() if not isinstance(v, dict)}
        results[scenario] = per_scenario
    return {"source_type": "synthetic", "research_only": True, "notice": NOTICE,
            "source_scenario": source, "model_version": source_meta["model_version"],
            "features": source_meta["n_features"], "calibration": source_meta["calibration"],
            "threshold": source_meta["threshold"], "policy": "frozen realistic winner applied unchanged",
            "ood_scenarios": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, default=Path("ml/runs/synthetic-v3"))
    parser.add_argument("--out", type=Path, default=Path("ml/runs/synthetic-v3"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(args.out / "baselines_v3.json", baselines(args.runs_root))
    write_json(args.out / "transfer_v3.json", transfer(args.runs_root))
    print("wrote", args.out / "baselines_v3.json", "and", args.out / "transfer_v3.json")
