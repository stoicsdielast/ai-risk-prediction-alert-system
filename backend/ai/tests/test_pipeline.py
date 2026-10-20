"""Retained, dataset-independent checks for the legacy prototype inference helpers.

The CSV-backed India milestone tests were retired: this project now trains on the
synthetic Fiji pipeline under ``ml/synthetic`` (see ``ml/tests/test_synthetic_*.py``
and ``backend/tests/test_v1_generation.py``). Nothing here reads the India dataset
or retrains a model; only configuration-light behaviour of ``ai.pipeline`` helpers
and generic sklearn pipeline semantics are exercised, using small in-memory frames.
"""

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

from ai.config import (
    CATEGORICAL_FEATURES, NUMERIC_FEATURES, TARGET_COLUMN,
)
from ai.predict import (
    load_model, probability_to_risk_level,
)
from ai.preprocessing import build_model_pipeline


@pytest.fixture
def synthetic_frame():
    """Small in-memory stand-in for a flood-occurrence frame (no external dataset)."""
    rng = np.random.default_rng(42)
    size = 200
    frame = pd.DataFrame({
        name: rng.normal(size=size) for name in NUMERIC_FEATURES
    })
    frame["Land Cover"] = rng.choice(["Forest", "Urban", "Agricultural"], size=size)
    frame["Soil Type"] = rng.choice(["Clay", "Loam", "Sandy"], size=size)
    frame[TARGET_COLUMN] = rng.integers(0, 2, size=size)
    return frame


@pytest.fixture
def trained(synthetic_frame):
    x_train = synthetic_frame[list(NUMERIC_FEATURES) + list(CATEGORICAL_FEATURES)]
    y_train = synthetic_frame[TARGET_COLUMN]
    model = build_model_pipeline(LogisticRegression(max_iter=1000, random_state=42))
    model.fit(x_train, y_train)
    model.flood_metadata_ = {
        "feature_columns": list(NUMERIC_FEATURES) + list(CATEGORICAL_FEATURES),
        "numeric_features": list(NUMERIC_FEATURES),
        "categorical_features": list(CATEGORICAL_FEATURES),
        "model_version": "unit-test-only-in-memory",
    }
    return model, x_train


def test_transformations_fit_only_supplied_rows(trained):
    model, x_train = trained
    numeric = model.named_steps["preprocessor"].named_transformers_["numeric"]
    np.testing.assert_allclose(
        numeric.named_steps["imputer"].statistics_, x_train[list(NUMERIC_FEATURES)].median(),
    )
    np.testing.assert_allclose(
        numeric.named_steps["scaler"].mean_, x_train[list(NUMERIC_FEATURES)].mean(),
    )
    assert TARGET_COLUMN not in model.feature_names_in_


def test_nulls_and_unseen_categories_are_handled_by_preprocessing(trained):
    model, _ = trained
    from ai.predict import predict_flood_probability
    sample = {name: 0.1 for name in NUMERIC_FEATURES}
    sample.update({"Land Cover": None, "Soil Type": "unseen-category-for-validation"})
    assert 0 <= predict_flood_probability(sample, model=model) <= 1


@pytest.mark.parametrize(("probability", "level"), [
    (0, "LOW"), (0.249999, "LOW"), (0.25, "MODERATE"), (0.499999, "MODERATE"),
    (0.5, "HIGH"), (0.749999, "HIGH"), (0.75, "VERY_HIGH"), (1, "VERY_HIGH"),
])
def test_risk_boundaries(probability, level):
    assert probability_to_risk_level(probability) == level


@pytest.mark.parametrize("probability", [-0.1, 1.1, float("nan"), float("inf")])
def test_invalid_probability(probability):
    with pytest.raises(ValueError):
        probability_to_risk_level(probability)


def test_thresholds_are_configurable():
    assert probability_to_risk_level(0.25, (0.1, 0.2, 0.3)) == "HIGH"
    with pytest.raises(ValueError):
        probability_to_risk_level(0.5, (0.5, 0.25, 0.75))


def test_load_missing_or_corrupt_model(tmp_path):
    with pytest.raises(ValueError, match="Model not found"):
        load_model(tmp_path / "missing.joblib")
    corrupt = tmp_path / "empty.joblib"
    corrupt.write_bytes(b"")
    with pytest.raises(ValueError, match="Unable to load model"):
        load_model(corrupt)
