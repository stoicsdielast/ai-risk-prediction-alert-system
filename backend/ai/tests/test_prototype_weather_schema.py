"""Verify the trained/inference contract matches the actual demo inputs."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ai.prototype_weather.schema import INPUT_COLUMNS, features_from_location, validate_inputs


@pytest.fixture
def prototype_location():
    return {
        "id": "nadi", "name": "Nadi", "division": "Western",
        "latitude": -17.7765, "longitude": 177.4356,
        "rainfall24hMm": 84, "temperatureC": 27, "humidityPercent": 89,
        "windKph": 20, "condition": "Heavy rain", "riskLevel": "HIGH",
        "updatedAt": "2025-01-01T00:00:00+12:00",
        "prediction": {"label": "High risk", "confidencePercent": 91, "summary": "Demo"},
        "officialWarning": "Demonstration warning",
    }


def test_exact_input_contract_matches_demo_input_artifact():
    assert INPUT_COLUMNS == [
        "latitude", "longitude", "rainfall24hMm", "temperatureC",
        "humidityPercent", "windKph",
    ]
    # The frontend WeatherLocation interface was removed when the prototype
    # dataset was replaced by live backend feeds; the predictor's flat
    # demo input shape now lives in the artifact JSON.
    artifact = Path(__file__).resolve().parents[1] / "artifacts/prototype_weather/example_location.json"
    example = json.loads(artifact.read_text())
    numeric_measurements = {
        key
        for key, value in example.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }
    assert numeric_measurements == set(INPUT_COLUMNS)


def test_inputs_are_float_and_output_changes_cannot_affect_features(prototype_location):
    original = features_from_location(prototype_location)
    prototype_location.update({
        "riskLevel": "LOW", "condition": "Dry",
        "prediction": {"label": "Low risk", "confidencePercent": 0, "summary": "Changed"},
        "officialWarning": None, "margin_lag2_ft": 900,
        "observed_flood_stage": 1, "flood_stage_ft": 7,
    })
    changed = features_from_location(prototype_location)
    pd.testing.assert_frame_equal(original, changed)
    assert original.columns.tolist() == INPUT_COLUMNS
    assert all(dtype == np.dtype("float64") for dtype in original.dtypes)


def test_nested_map_location_uses_root_coordinates(prototype_location):
    payload = {
        "latitude": -18.1416, "longitude": 178.4419,
        "conditions": prototype_location,
        "prediction": {"floodProbabilityPercent": 99}, "riskLevel": "VERY_HIGH",
    }
    features = features_from_location(payload)
    assert features.iloc[0]["latitude"] == -18.1416
    assert features.iloc[0]["longitude"] == 178.4419
    assert features.iloc[0]["rainfall24hMm"] == 84


@pytest.mark.parametrize("nested", [False, True])
def test_missing_wind_is_rejected_instead_of_imputed(prototype_location, nested):
    del prototype_location["windKph"]
    payload = {"conditions": prototype_location} if nested else prototype_location
    with pytest.raises(ValueError, match="Missing.*windKph"):
        features_from_location(payload)


@pytest.mark.parametrize("field,value", [
    ("latitude", -90.01), ("latitude", 90.01),
    ("longitude", -180.01), ("longitude", 180.01),
    ("rainfall24hMm", -0.01), ("temperatureC", -273.16),
    ("humidityPercent", -0.01), ("humidityPercent", 100.01),
    ("windKph", -0.01),
])
def test_out_of_range_weather_is_rejected(prototype_location, field, value):
    prototype_location[field] = value
    with pytest.raises(ValueError, match=field):
        features_from_location(prototype_location)


@pytest.mark.parametrize("value", [True, np.bool_(False), np.nan, np.inf, -np.inf, None, "unknown", 1 + 2j])
def test_invalid_measurement_is_rejected(prototype_location, value):
    prototype_location["windKph"] = value
    with pytest.raises(ValueError, match="windKph"):
        features_from_location(prototype_location)


def test_extreme_finite_values_do_not_get_arbitrary_upper_limits(prototype_location):
    prototype_location.update({
        "latitude": -90, "longitude": 180, "rainfall24hMm": 10000,
        "temperatureC": -273.15, "humidityPercent": 100, "windKph": 10000,
    })
    assert len(features_from_location(prototype_location)) == 1


def test_numeric_strings_convert_and_source_is_not_mutated(prototype_location):
    source = pd.DataFrame([{**prototype_location, "windKph": "20.5"}], index=[42])
    result = validate_inputs(source)
    assert result.loc[42, "windKph"] == 20.5
    assert source.loc[42, "windKph"] == "20.5"
    assert "prediction" in source


@pytest.mark.parametrize("payload", [None, [], {"conditions": None}])
def test_absent_or_invalid_conditions_fail_clearly(payload):
    with pytest.raises(ValueError):
        features_from_location(payload)


def test_duplicate_columns_and_dates_are_not_numeric_measurements(prototype_location):
    source = pd.DataFrame([prototype_location])
    duplicate = pd.concat([source, source[["windKph"]]], axis=1)
    with pytest.raises(ValueError, match="unique"):
        validate_inputs(duplicate)
    source["windKph"] = pd.Timestamp("2025-01-01")
    with pytest.raises(ValueError, match="windKph"):
        validate_inputs(source)
