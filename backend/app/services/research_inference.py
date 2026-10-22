"""Lazy, cached artifact loading; requests never download or train a model."""
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path


class ModelUnavailable(Exception):
    pass


class InvalidResearchInput(ValueError):
    pass


def presentation_tier(probability, thresholds):
    result = "LOW"
    for name in ("MODERATE", "HIGH", "VERY_HIGH"):
        if probability >= thresholds[name]:
            result = name
    return result


class ResearchModel:
    def __init__(self, directory):
        directory = Path(directory)
        self.metadata = json.loads((directory / "model_metadata.json").read_text())
        self.schema = json.loads((directory / "feature_schema.json").read_text())
        self.thresholds = json.loads((directory / "thresholds.json").read_text())
        self.registry = json.loads((directory / "stations.json").read_text())
        self.provenance = json.loads((directory / "provenance.json").read_text())
        self.directory = directory
        if self.metadata.get("research_mode") is not True or self.metadata.get("smoke_only"):
            raise ValueError("Only complete research artifacts can be served")
        self.features = self.schema["features"]
        if not self.features or len(set(self.features)) != len(self.features) or any(
            any(part in feature.lower() for part in ("flood", "regime", "target", "future")) for feature in self.features
        ):
            raise ValueError("Invalid inference feature schema")
        levels = [self.thresholds["presentation_tiers"][name] for name in ("MODERATE", "HIGH", "VERY_HIGH")]
        if not 0 < levels[0] < levels[1] < levels[2] < 1 or not 0 <= self.thresholds["binary_threshold"] <= 1:
            raise ValueError("Invalid threshold configuration")
        binary = directory / "classifier.joblib"
        if hashlib.sha256(binary.read_bytes()).hexdigest() != self.metadata["classifier_sha256"]:
            raise ValueError("Classifier integrity check failed")
        # Only locally trained/trusted binaries belong in this operator-owned
        # directory. Never accept uploaded pickle/joblib objects.
        import joblib
        import sklearn
        if sklearn.__version__ != self.metadata["versions"]["scikit-learn"]:
            raise ValueError("Training/inference scikit-learn versions differ")
        self.pipeline = joblib.load(binary)
        if list(self.pipeline.feature_names_in_) != self.features or list(self.pipeline.classes_) != [0, 1]:
            raise ValueError("Classifier/schema mismatch")

    def predict(self, request):
        unknown = set(request.features) - set(self.features)
        if unknown:
            raise InvalidResearchInput("Unknown or training-only features: " + ", ".join(sorted(unknown)))
        if request.station_id not in self.registry:
            raise InvalidResearchInput("Unsupported Bangladesh source station")
        if not "1950-01-01" <= request.feature_date.isoformat() <= "2026-08-07":
            raise InvalidResearchInput("Date is outside the pinned historical dataset")
        missing = [c for c in self.features if request.features.get(c) is None]
        if missing:
            return None, missing
        values = request.features
        station = self.registry[request.station_id]
        for key in self.features:
            value = values[key]
            try:
                finite = math.isfinite(value)
            except (OverflowError, TypeError):
                finite = False
            if not finite:
                raise InvalidResearchInput(f"{key} must be finite")
            if key.startswith(("rainfall_", "river_discharge_")) or key == "hand_m":
                if value < 0:
                    raise InvalidResearchInput(f"{key} must be non-negative")
            if key.startswith("soil_moisture_") and not 0 <= value <= 1:
                raise InvalidResearchInput(f"{key} must be a volumetric fraction from 0 to 1")
        for coordinate in ("latitude", "longitude"):
            if abs(values[coordinate] - station[coordinate]) > 1e-5:
                raise InvalidResearchInput("Coordinates do not match the source station")
        import pandas as pd
        try:
            probability = float(self.pipeline.predict_proba(pd.DataFrame([{c: values[c] for c in self.features}]))[0, 1])
        except Exception as error:
            raise ModelUnavailable("Research inference failed; verify compatible local artifacts") from error
        if not math.isfinite(probability) or not 0 <= probability <= 1:
            raise ModelUnavailable("Model produced an invalid probability")
        return probability, []


@lru_cache(maxsize=2)
def load_model(directory: str):
    try:
        return ResearchModel(directory)
    except Exception as error:
        raise ModelUnavailable("Research model artifacts unavailable or incompatible; train/verify the pinned research pipeline") from error
