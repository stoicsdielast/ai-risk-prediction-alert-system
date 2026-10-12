"""Validate transformations and inference with real rows from the source CSV."""

import json

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

from ai.config import (
    CATEGORICAL_FEATURES, DEFAULT_DATASET, FEATURE_COLUMNS, NUMERIC_FEATURES,
    TARGET_COLUMN,
)
from ai.evaluate import evaluate_model
from ai.inspection import read_dataset, validate_dataset
from ai.predict import (
    load_model, predict_flood_probability, predict_flood_risk, probability_to_risk_level,
)
from ai.preprocessing import build_model_pipeline


@pytest.fixture(scope="module")
def source():
    return read_dataset(DEFAULT_DATASET)


@pytest.fixture(scope="module")
def trained(source):
    # Real CSV records; a small training subset keeps verification fast.
    subset = source.iloc[:400]
    x_train, x_test, y_train, y_test = train_test_split(
        subset[list(FEATURE_COLUMNS)], subset[TARGET_COLUMN],
        test_size=0.2, random_state=42, stratify=subset[TARGET_COLUMN],
    )
    model = build_model_pipeline(LogisticRegression(max_iter=1000, random_state=42))
    model.fit(x_train, y_train)
    model.flood_metadata_ = {
        "feature_columns": list(FEATURE_COLUMNS),
        "numeric_features": list(NUMERIC_FEATURES),
        "categorical_features": list(CATEGORICAL_FEATURES),
        "model_version": "unit-test-only-real-csv-subset",
    }
    return model, x_train, x_test, y_test


def test_transformations_fit_only_training_rows(trained):
    model, x_train, x_test, _ = trained
    numeric = model.named_steps["preprocessor"].named_transformers_["numeric"]
    np.testing.assert_allclose(
        numeric.named_steps["imputer"].statistics_, x_train[list(NUMERIC_FEATURES)].median(),
    )
    np.testing.assert_allclose(
        numeric.named_steps["scaler"].mean_, x_train[list(NUMERIC_FEATURES)].mean(),
    )
    assert set(x_train.index).isdisjoint(x_test.index)
    assert "Historical Floods" not in model.feature_names_in_
    assert TARGET_COLUMN not in model.feature_names_in_


def test_saved_pipeline_reproduces_probability_and_metadata(trained, tmp_path):
    model, _, x_test, _ = trained
    path = tmp_path / "model.joblib"
    joblib.dump(model, path)
    loaded = load_model(path)
    sample = x_test.iloc[0].to_dict()
    expected = model.predict_proba(x_test.iloc[[0]])[0, list(model.classes_).index(1)]
    assert predict_flood_probability(sample, model=loaded) == pytest.approx(expected)
    result = predict_flood_risk(sample, model=loaded)
    assert result["model_version"] == model.flood_metadata_["model_version"]
    assert result["confidence_percent"] == pytest.approx(expected * 100)
    assert result["risk_level"] == probability_to_risk_level(expected)
    json.dumps(result, allow_nan=False)


def test_nulls_and_unseen_categories_are_handled_by_saved_preprocessing(trained):
    model, _, x_test, _ = trained
    sample = x_test.iloc[0].to_dict()
    sample["Rainfall (mm)"] = None
    sample["Land Cover"] = None
    sample["Soil Type"] = "unseen-category-for-validation"
    assert 0 <= predict_flood_probability(sample, model=model) <= 1


@pytest.mark.parametrize("change", [
    "missing_feature", "target_included", "excluded_history", "invalid_numeric", "infinite_numeric",
])
def test_invalid_input_fails_clearly(trained, change):
    model, _, x_test, _ = trained
    sample = x_test.iloc[0].to_dict()
    if change == "missing_feature":
        sample.pop("Rainfall (mm)")
    elif change == "target_included":
        sample[TARGET_COLUMN] = 1
    elif change == "excluded_history":
        sample["Historical Floods"] = 0
    elif change == "invalid_numeric":
        sample["Rainfall (mm)"] = "invalid-number-for-validation"
    else:
        sample["Rainfall (mm)"] = float("inf")
    with pytest.raises(ValueError):
        predict_flood_probability(sample, model=model)


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


def test_evaluation_uses_actual_predictions(trained):
    model, _, x_test, y_test = trained
    result = evaluate_model(model, x_test, y_test)
    matrix = np.array(result["confusion_matrix"])
    assert matrix.sum() == len(y_test)
    assert result["recall"] == pytest.approx(matrix[1, 1] / matrix[1].sum())
    assert result["accuracy"] == pytest.approx(np.trace(matrix) / matrix.sum())


def test_dataset_validation_rejects_duplicate_rows_and_missing_labels(source):
    validate_dataset(source)
    with pytest.raises(ValueError, match="Repeated feature rows"):
        validate_dataset(pd.concat([source, source.iloc[[0]]], ignore_index=True))
    missing_label = source.copy()
    missing_label.loc[0, TARGET_COLUMN] = np.nan
    with pytest.raises(ValueError, match="no missing labels"):
        validate_dataset(missing_label)


def test_load_missing_or_corrupt_model(tmp_path):
    with pytest.raises(ValueError, match="Model not found"):
        load_model(tmp_path / "missing.joblib")
    corrupt = tmp_path / "empty.joblib"
    corrupt.write_bytes(b"")
    with pytest.raises(ValueError, match="Unable to load model"):
        load_model(corrupt)
