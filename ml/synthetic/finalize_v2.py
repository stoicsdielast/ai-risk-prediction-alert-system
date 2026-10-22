"""Reconstruct the validation-selected v2 winner deterministically and save a local candidate bundle.

Does not publish to the serving directory and does not touch reserved evaluations.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import IsotonicRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml.refinement import sha256
from ml.train import write_json
from ml.training03 import fit_sigmoid
from ml.synthetic.features_v2 import build_features_v2
from ml.synthetic.generate import NOTICE
from ml.synthetic.train import partition
from ml.synthetic.train_v2 import fit_model


def package(dataset, run):
    run = Path(run)
    lock = json.loads((run / "selection_lock.json").read_text())
    winner = lock["selected"]
    best = json.loads((run / "best_params.json").read_text())[winner]
    thresholds = json.loads((run / "thresholds.json").read_text())
    calibration = pd.read_csv(run / "calibration_comparison.csv")
    valid = calibration[calibration.feasible].sort_values(["ece_equal_width_10_bins", "brier", "method"])
    method = valid.iloc[0].method if not valid.empty else "none"

    dataset = Path(dataset)
    meta = json.loads((dataset / "dataset_metadata.json").read_text())
    loc = pd.read_csv(dataset / "locations.csv")
    obs = pd.read_parquet(dataset / "weather_observations.parquet")
    labels = pd.read_parquet(dataset / "training_labels.parquet")
    scenarios = pd.read_csv(dataset / "simulation_scenarios.csv", parse_dates=["start", "end"])
    features, extended, weather_only = build_features_v2(obs, loc, meta["config"]["frequency"])
    frame = features.merge(labels, on=["location_id", "timestamp"], validate="one_to_one")
    frame["stage"], _ = partition(frame, scenarios)
    names = best["features"]
    if names == "weather_only":
        names = weather_only
    elif names == "extended":
        names = extended
    parts = {s: frame[frame.stage.eq(s)].copy() for s in ["train", "calibration", "selection", "threshold", "test"]}

    family = best["family"]
    if family in ("catboost", "lightgbm"):
        estimator = fit_model(family, best["params"], parts["train"], parts["calibration"], names)
    else:
        inner = (LogisticRegression(C=1., class_weight="balanced", max_iter=1500, random_state=314)
                 if family == "sklearn" and winner.startswith("logistic")
                 else RandomForestClassifier(n_estimators=160, max_depth=14, min_samples_leaf=10,
                                             class_weight="balanced_subsample", n_jobs=4, random_state=314))
        estimator = Pipeline([("imputer", SimpleImputer(strategy="median", add_indicator=True)),
                              ("scale", StandardScaler()), ("classifier", inner)])
        estimator.fit(parts["train"][names], parts["train"].flood_within_24h.astype(int))

    raw_cal = estimator.predict_proba(parts["calibration"][names])[:, 1]
    calibrator = {"none": None, "sigmoid": fit_sigmoid(raw_cal, parts["calibration"].flood_within_24h),
                  "isotonic": IsotonicRegression(out_of_bounds="clip").fit(raw_cal, parts["calibration"].flood_within_24h)}[method]
    bundle = {"model": estimator, "calibrator": calibrator, "features": names,
              "threshold": float(thresholds[winner]["threshold"]),
              "model_version": f"synthetic-fiji-v2-{winner}__{method}", "source_type": "synthetic"}
    model_path = run / "selected_model.joblib"
    joblib.dump(bundle, model_path)
    write_json(run / "model_metadata.json", {"model_version": bundle["model_version"], "selected_candidate": winner,
        "calibration": method, "threshold": bundle["threshold"], "source_type": "synthetic", "notice": NOTICE,
        "dataset": str(dataset.resolve()), "dataset_metadata_sha256": sha256(dataset / "dataset_metadata.json"),
        "features": names, "n_features": len(names), "model_sha256": sha256(model_path),
        "packaged_at": datetime.now(timezone.utc).isoformat(),
        "risk_tiers": "Provisional research bands relative to validation threshold: LOW <0.5t, MODERATE <t, HIGH <min(1,1.5t), VERY_HIGH otherwise"})
    write_json(run / "feature_schema.json", {"source_type": "synthetic", "features": names, "frequency": meta["config"]["frequency"],
        "historically_recomputable": True, "note": "All features use current/past observations only and are recomputed from raw history."})
    if not (run / "simulation_outcomes.parquet").exists():
        labels[["location_id", "timestamp", "flood_occurred"]].to_parquet(run / "simulation_outcomes.parquet", index=False)
    manifest = {p.name: sha256(p) for p in run.iterdir() if p.name not in ("features.parquet",) and p.is_file()}
    write_json(run / "candidate_manifest.json", {"model_version": bundle["model_version"], "candidate_only": True,
        "published": False, "hashes": manifest})
    print(json.dumps({"winner": winner, "calibration": method, "threshold": bundle["threshold"],
                      "n_features": len(names), "model_sha256": sha256(model_path)}, indent=2))
    return bundle


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("ml/data/synthetic_fiji/v1"))
    parser.add_argument("--run", type=Path, default=Path("ml/runs/synthetic-v2"))
    args = parser.parse_args()
    package(args.dataset, args.run)
