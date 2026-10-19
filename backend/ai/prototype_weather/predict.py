"""Run the six-input POC on a prototype JSON location or historical rows."""

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from threadpoolctl import threadpool_limits

from ai.prototype_weather.data import DATA_DIR
from ai.prototype_weather.schema import INPUT_COLUMNS, features_from_location, validate_inputs
from ai.prototype_weather.train import MODEL_DIR, MODEL_PREFIX, validate_dataset


def load_model(model_path: Path) -> dict:
    # Joblib files execute code when loaded: use only locally trained, trusted files.
    bundle = joblib.load(model_path)
    metadata = bundle["metadata"]
    if (metadata.get("input_columns") != INPUT_COLUMNS
            or not metadata.get("model_version", "").startswith(MODEL_PREFIX)
            or list(bundle["pipeline"].feature_names_in_) != INPUT_COLUMNS):
        raise ValueError("Not a compatible six-input prototype weather model")
    return bundle


def run_predictions(bundle: dict, inputs: pd.DataFrame) -> dict:
    inputs = validate_inputs(inputs)
    metadata = bundle["metadata"]
    with threadpool_limits(limits=1):
        probabilities = bundle["pipeline"].predict_proba(inputs)[:, 1]
    return {
        "model_version": metadata["model_version"],
        "input_columns": INPUT_COLUMNS,
        "target": metadata["target"], "decision_threshold": metadata["decision_threshold"],
        "prototype_input_compatible": True, "development_only": True,
        "evaluation_kind": "RETROSPECTIVE_REANALYSIS_POC",
        "fiji_validated": False, "operational_forecast_validated": False, "calibrated": False,
        "predictions": [{
            "flood_stage_probability": float(probability),
            "predicted_flood_stage": bool(probability >= metadata["decision_threshold"]),
            "outside_training_ranges": [
                name for name in INPUT_COLUMNS
                if not metadata["training_input_ranges"][name]["min"] <= row[name] <= metadata["training_input_ranges"][name]["max"]
            ],
        } for row, probability in zip(inputs.to_dict(orient="records"), probabilities)],
    }


def predict_location(model_path: Path, payload: dict) -> dict:
    """Accept WeatherLocation or MapLocation fields; output fields are ignored."""
    result = run_predictions(load_model(model_path), features_from_location(payload))
    result["historical_demo"] = False
    return result


def predict_historical(model_path: Path, dataset_path: Path, forecast_date: str | None = None) -> dict:
    frame = validate_dataset(pd.read_csv(dataset_path))
    day = forecast_date or frame["forecast_date"].max()
    rows = frame[frame["forecast_date"].eq(day)].copy()
    if rows.empty:
        raise ValueError(f"No complete historical observations for {day}")
    result = run_predictions(load_model(model_path), rows)
    result.update({
        "historical_demo": True, "forecast_date": day,
        "areas_without_complete_data": sorted(set(frame["area_id"]) - set(rows["area_id"])),
    })
    for prediction, row in zip(result["predictions"], rows.to_dict(orient="records")):
        prediction.update({key: row[key] for key in ("area_id", "issued_at", "window_end", "observed_flood_stage")})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=MODEL_DIR / "prototype_weather_model.joblib")
    parser.add_argument("--dataset", type=Path, default=DATA_DIR / "dataset.csv")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--input", type=Path, help="JSON WeatherLocation or MapLocation with the six demo fields")
    source.add_argument("--date", help="Historical date; defaults to the latest labelled day")
    args = parser.parse_args()
    try:
        result = (predict_location(args.model, json.loads(args.input.read_text())) if args.input
                  else predict_historical(args.model, args.dataset, args.date))
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"Demo weather prediction failed: {error}\n")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
