"""Run the saved river POC on historical rows; never publish alerts."""

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd

from ai.river.data import DATA_DIR, INPUT_COLUMNS
from ai.river.train import MODEL_DIR, validate_dataset


def predict(model_path: Path, dataset_path: Path, forecast_date: str | None = None) -> dict:
    # Only load locally trained, trusted joblib artifacts.
    bundle = joblib.load(model_path)
    metadata = bundle["metadata"]
    if metadata.get("input_columns") != INPUT_COLUMNS or not metadata.get("model_version", "").startswith("us-river-next24h-poc-"):
        raise ValueError("Not a compatible US river proof-of-concept model")
    frame = validate_dataset(pd.read_csv(dataset_path, dtype={"usgs_id": str}))
    day = forecast_date or frame["forecast_date"].max()
    rows = frame[frame["forecast_date"] == day].copy()
    if rows.empty:
        raise ValueError(f"No complete historical observations for {day}")
    probabilities = bundle["pipeline"].predict_proba(rows[INPUT_COLUMNS])[:, 1]
    return {
        "model_version": metadata["model_version"], "historical_demo": True,
        "fiji_validated": False, "forecast_date": day,
        "areas_without_complete_data": sorted(set(frame["area_id"]) - set(rows["area_id"])),
        "target": metadata["target"], "decision_threshold": metadata["decision_threshold"],
        "predictions": [{
            "area_id": row["area_id"], "issued_at": row["issued_at"], "window_end": row["window_end"],
            "flood_stage_probability": float(probability),
            "predicted_flood_stage": bool(probability >= metadata["decision_threshold"]),
            "observed_flood_stage": int(row["observed_flood_stage"]),
        } for row, probability in zip(rows.to_dict(orient="records"), probabilities)],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=MODEL_DIR / "river_flood_model.joblib")
    parser.add_argument("--dataset", type=Path, default=DATA_DIR / "dataset.csv")
    parser.add_argument("--date")
    args = parser.parse_args()
    try:
        result = predict(args.model, args.dataset, args.date)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"River prediction failed: {error}\n")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
