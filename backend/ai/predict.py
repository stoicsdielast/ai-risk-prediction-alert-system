"""Standalone inference using the saved, complete sklearn pipeline."""

import argparse
import json
import math
import pickle
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from .config import MODEL_PATH, PROCESSED_DIR, RISK_THRESHOLDS


def load_model(model_path: Path | str = MODEL_PATH) -> Pipeline:
    """Load a locally trained pipeline; joblib files must come from trusted sources."""
    path = Path(model_path)
    if not path.is_file():
        raise ValueError(f"Model not found: {path}. Run python -m ai.train from backend first.")
    try:
        model = joblib.load(path)
    except (OSError, ValueError, EOFError, pickle.UnpicklingError, ImportError, AttributeError) as error:
        raise ValueError(f"Unable to load model {path.name}: {error}") from error
    if not isinstance(model, Pipeline) or not hasattr(model, "flood_metadata_"):
        raise ValueError("Expected a complete flood pipeline with training metadata.")
    return model


def probability_to_risk_level(
    probability: float, thresholds: tuple[float, float, float] = RISK_THRESHOLDS,
) -> str:
    """Map a flood probability to configurable, unvalidated prototype risk bands."""
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError("Flood probability must be finite and between 0 and 1.")
    if len(thresholds) != 3 or not 0 < thresholds[0] < thresholds[1] < thresholds[2] < 1:
        raise ValueError("Risk thresholds must be three increasing values strictly between 0 and 1.")
    for threshold, level in zip(thresholds, ("LOW", "MODERATE", "HIGH")):
        if probability < threshold:
            return level
    return "VERY_HIGH"


def prepare_input(input_data: Mapping[str, Any], model: Pipeline) -> pd.DataFrame:
    if not isinstance(input_data, Mapping):
        raise ValueError("Input must be a mapping of exact feature names to values.")
    metadata = model.flood_metadata_
    columns = metadata["feature_columns"]
    missing = set(columns) - set(input_data)
    unexpected = set(input_data) - set(columns)
    if missing or unexpected:
        raise ValueError(
            f"Invalid input fields. Missing: {sorted(missing)}; unexpected: {sorted(unexpected)}. "
            "Supply all feature keys; use null for missing measurements."
        )
    frame = pd.DataFrame([{name: input_data[name] for name in columns}])
    for name in metadata["numeric_features"]:
        try:
            frame[name] = pd.to_numeric(frame[name], errors="raise").astype(float)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Feature {name!r} must be numeric or null.") from error
        if np.isinf(frame[name].to_numpy()).any():
            raise ValueError(f"Feature {name!r} must be finite or null.")
    for name in metadata["categorical_features"]:
        value = input_data[name]
        if value is not None and not isinstance(value, str):
            raise ValueError(f"Feature {name!r} must be a category string or null.")
        frame[name] = pd.Series([np.nan if value is None else value], dtype=object)
    return frame


def predict_flood_probability(
    input_data: Mapping[str, Any], *, model: Pipeline | None = None,
    model_path: Path | str = MODEL_PATH,
) -> float:
    pipeline = model if model is not None else load_model(model_path)
    frame = prepare_input(input_data, pipeline)
    classes = list(pipeline.classes_)
    if 1 not in classes:
        raise ValueError("Saved model has no flood class (1).")
    return float(pipeline.predict_proba(frame)[0, classes.index(1)])


def predict_flood_risk(
    input_data: Mapping[str, Any], *, model: Pipeline | None = None,
    model_path: Path | str = MODEL_PATH,
    thresholds: tuple[float, float, float] = RISK_THRESHOLDS,
) -> dict[str, Any]:
    pipeline = model if model is not None else load_model(model_path)
    probability = predict_flood_probability(input_data, model=pipeline)
    return {
        "flood_probability": probability,
        # This is P(flood) * 100, not a calibrated confidence in prediction correctness.
        "confidence_percent": probability * 100,
        "risk_level": probability_to_risk_level(probability, thresholds),
        "model_version": pipeline.flood_metadata_["model_version"],
        "predicted_at": datetime.now(timezone.utc).isoformat(),
    }


def print_test_prediction(sample: dict[str, Any], result: dict[str, Any]) -> None:
    print("\n========================================")
    print("FLOOD RISK AI - TEST PREDICTION")
    print("========================================")
    print("Input (original CSV row index:", sample["source_row_index"], ")")
    for name, value in sample["input_data"].items():
        print(f"{name}: {value}")
    print(f"Flood Probability: {result['flood_probability']:.6f}")
    print("Risk Level:", result["risk_level"])
    print("Actual Dataset Label:", sample["actual_label"])
    print("Model Version:", result["model_version"])
    print("Prototype thresholds; probability estimates are not calibrated warning confidence.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=MODEL_PATH)
    parser.add_argument("--input", type=Path, help="JSON object with the exact 12 feature keys")
    args = parser.parse_args()
    try:
        pipeline = load_model(args.model)
        if args.input:
            input_data = json.loads(args.input.read_text(encoding="utf-8"))
            print(json.dumps(predict_flood_risk(input_data, model=pipeline), indent=2))
        else:
            sample = json.loads((PROCESSED_DIR / "test_sample.json").read_text(encoding="utf-8"))
            if sample["model_version"] != pipeline.flood_metadata_["model_version"]:
                raise ValueError("Sample belongs to another training run. Use its model or supply --input.")
            result = predict_flood_risk(sample["input_data"], model=pipeline)
            print_test_prediction(sample, result)
            print(json.dumps(result, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Prediction failed: {error}\n")


if __name__ == "__main__":
    main()
