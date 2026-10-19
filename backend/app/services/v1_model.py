"""Read-only V1 artifact loader: no replay feature lookup and no training."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np

from app.services.synthetic_inference import risk_category


class V1ModelUnavailable(RuntimeError):
    pass


def file_sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class V1Model:
    def __init__(self, directory):
        directory = Path(directory)
        self.metadata = json.loads((directory / "model_metadata.json").read_text())
        self.sha256 = file_sha256(directory / "selected_model.joblib")
        if self.sha256 != self.metadata["model_sha256"]:
            raise ValueError("V1 checksum mismatch")
        if self.metadata["model_version"] != "synthetic-fiji-v1-catboost__none":
            raise ValueError("Only the selected V1 CatBoost model is permitted")
        self.bundle = joblib.load(directory / "selected_model.joblib")
        self.features = self.bundle["features"]
        if (self.bundle["source_type"] != "synthetic" or self.bundle["model_version"] != self.metadata["model_version"]
                or self.features != self.metadata["features"] or self.bundle["calibrator"] is not None):
            raise ValueError("V1 bundle contract mismatch")
        if hashlib.sha256(json.dumps(self.features).encode()).hexdigest() != self.metadata["feature_schema_sha256"]:
            raise ValueError("V1 feature schema checksum mismatch")

    def predict(self, features):
        try:
            probability = float(self.bundle["model"].predict_proba(features[self.features])[0, 1])
            if not np.isfinite(probability) or not 0 <= probability <= 1:
                raise ValueError("Non-finite model output")
            return probability, risk_category(probability, self.bundle["threshold"])
        except Exception as error:
            raise V1ModelUnavailable("V1 inference failed; no prediction was saved") from error


@lru_cache(maxsize=2)
def load_v1_model(directory):
    try:
        return V1Model(directory)
    except Exception as error:
        raise V1ModelUnavailable("Selected V1 model unavailable or incompatible") from error
