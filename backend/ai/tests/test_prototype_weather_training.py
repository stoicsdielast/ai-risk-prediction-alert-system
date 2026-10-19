"""Synthetic fixtures verify training isolation, not real predictive performance."""

import json

import joblib
import numpy as np
import pandas as pd
import pytest

from ai.prototype_weather.schema import INPUT_COLUMNS
from ai.prototype_weather.predict import predict_historical, predict_location
from ai.prototype_weather.train import TARGET, select_threshold, train, validate_dataset
from ai.river.train import split_dataset


@pytest.fixture
def labelled_weather():
    """Artificial separated flood episodes for checking pipeline mechanics only."""
    index = pd.date_range("2020-01-01", periods=240, tz="UTC")
    day = np.arange(len(index))
    flooded = (day % 20 < 3).astype(int)
    return pd.DataFrame({
        "area_id": "synthetic-test-town", "river_system": "synthetic-test-river",
        "forecast_date": index.strftime("%Y-%m-%d"),
        "issued_at": index.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "window_end": (index + pd.Timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "weather_reference_at": index.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "rain_window_start": (index - pd.Timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "weather_source_kind": "ERA5_REANALYSIS",
        "latitude": 41.5, "longitude": -91.5,
        "rainfall24hMm": np.where(day % 20 < 5, 40.0, 4.0),
        "temperatureC": 20.0 + np.sin(day / 10),
        "humidityPercent": 65.0 + np.cos(day / 10),
        "windKph": 10.0 + np.sin(day / 5),
        TARGET: flooded,
        "target_max_stage_ft": np.where(flooded, 8.0, 3.0),
        "approved_samples": 96, "flood_stage_ft": 7.0,
        "label_source": "https://example.org/synthetic-observation-unit-fixture",
        "threshold_source": "https://example.org/synthetic-threshold-unit-fixture",
        "reference_persistence": np.roll(flooded, 2),
    })


@pytest.mark.parametrize("problem", [
    "missing_wind", "null_weather", "missing_timing", "reference_after_issue",
    "rain_in_target_window", "wrong_target_end", "issue_date_mismatch",
    "label_mismatch", "invalid_label", "incomplete_coverage",
    "missing_label_source", "invalid_threshold_source", "wrong_weather_source",
    "duplicate_day", "nonfinite_stage", "invalid_benchmark",
])
def test_training_rejects_incomplete_or_inconsistent_records(labelled_weather, problem):
    data = labelled_weather.copy()
    if problem == "missing_wind":
        data = data.drop(columns="windKph")
    elif problem == "null_weather":
        data.loc[0, "rainfall24hMm"] = np.nan
    elif problem == "missing_timing":
        data = data.drop(columns="weather_reference_at")
    elif problem == "reference_after_issue":
        data.loc[0, "weather_reference_at"] = "2020-01-01T01:00:00+00:00"
    elif problem == "rain_in_target_window":
        data.loc[0, "rain_window_start"] = "2020-01-01T00:00:00+00:00"
    elif problem == "wrong_target_end":
        data.loc[0, "window_end"] = "2020-01-03T00:00:00+00:00"
    elif problem == "issue_date_mismatch":
        data.loc[0, "forecast_date"] = "2019-12-31"
    elif problem == "label_mismatch":
        data.loc[0, TARGET] = 0
    elif problem == "invalid_label":
        data.loc[0, TARGET] = 2
    elif problem == "incomplete_coverage":
        data.loc[0, "approved_samples"] = 95
    elif problem == "missing_label_source":
        data.loc[0, "label_source"] = ""
    elif problem == "invalid_threshold_source":
        data.loc[0, "threshold_source"] = "guessed threshold"
    elif problem == "wrong_weather_source":
        data.loc[0, "weather_source_kind"] = "LIVE_OBSERVATION"
    elif problem == "duplicate_day":
        data = pd.concat([data, data.iloc[[0]]], ignore_index=True)
    elif problem == "nonfinite_stage":
        data.loc[0, "target_max_stage_ft"] = np.inf
    elif problem == "invalid_benchmark":
        data.loc[0, "reference_persistence"] = 2
    with pytest.raises(ValueError):
        validate_dataset(data)


def test_weather_splits_use_separated_dates_and_flood_episodes(labelled_weather):
    parts = split_dataset(validate_dataset(labelled_weather), "2020-03-01", "2020-05-01", 8)
    assert parts["train"]["forecast_date"].max() == "2020-02-21"
    assert parts["validation"]["forecast_date"].min() == "2020-03-01"
    assert parts["validation"]["forecast_date"].max() == "2020-04-22"
    assert parts["test"]["forecast_date"].min() == "2020-05-01"
    episodes = {}
    for name, part in parts.items():
        assert set(part[TARGET]) == {0, 1}
        episodes[name] = set(part.loc[part[TARGET].eq(1), "event_id"])
    assert episodes["train"].isdisjoint(episodes["validation"])
    assert episodes["train"].isdisjoint(episodes["test"])
    assert episodes["validation"].isdisjoint(episodes["test"])


def test_saved_six_input_model_and_selection_ignore_final_test_labels(labelled_weather, tmp_path):
    data = labelled_weather.copy()
    path = tmp_path / "synthetic_unit_fixture.csv"
    data.to_csv(path, index=False)
    output = tmp_path / "first"
    report = train(path, output, "2020-03-01", "2020-05-01", 8)
    bundle = joblib.load(output / "prototype_weather_model.joblib")
    model = bundle["pipeline"]
    assert model.feature_names_in_.tolist() == INPUT_COLUMNS
    assert model.n_features_in_ == 6
    assert bundle["metadata"]["input_columns"] == INPUT_COLUMNS
    assert report["prototype_input_compatible"]
    assert report["development_only"]
    assert report["evaluation_kind"] == "RETROSPECTIVE_REANALYSIS_POC"
    assert not report["fiji_validated"]
    assert not report["operational_forecast_validated"]
    assert not report["calibrated"]
    json.dumps(report, allow_nan=False)

    saved = pd.read_csv(output / "test_predictions.csv")
    rows = saved.merge(data, on=["area_id", "forecast_date"], suffixes=("_saved", ""), validate="one_to_one")
    np.testing.assert_allclose(saved["flood_stage_probability"], model.predict_proba(rows[INPUT_COLUMNS])[:, 1])
    np.testing.assert_array_equal(
        saved["predicted_flood_stage"],
        (saved["flood_stage_probability"] >= report["decision_threshold"]).astype(int),
    )
    assert json.loads((output / "training_report.json").read_text())["input_columns"] == INPUT_COLUMNS

    historical = predict_historical(output / "prototype_weather_model.joblib", path)
    assert historical["historical_demo"]
    assert historical["forecast_date"] == data["forecast_date"].max()
    last_row = data.iloc[-1]
    flat = {name: float(last_row[name]) for name in INPUT_COLUMNS}
    flat["prediction"] = {"confidencePercent": 100}
    flat["observed_flood_stage"] = 1 - int(last_row[TARGET])
    location = predict_location(output / "prototype_weather_model.joblib", flat)
    assert location["predictions"][0]["flood_stage_probability"] == pytest.approx(historical["predictions"][0]["flood_stage_probability"])
    nested = {"latitude": flat["latitude"], "longitude": flat["longitude"], "conditions": {
        name: flat[name] for name in INPUT_COLUMNS if name not in ("latitude", "longitude")
    }}
    assert predict_location(output / "prototype_weather_model.joblib", nested) == location
    assert not location["historical_demo"] and not location["fiji_validated"]
    assert "observed_flood_stage" not in location["predictions"][0]
    nested["latitude"] = -18.0
    assert "latitude" in predict_location(output / "prototype_weather_model.joblib", nested)["predictions"][0]["outside_training_ranges"]
    nested["conditions"].pop("windKph")
    with pytest.raises(ValueError, match="windKph"):
        predict_location(output / "prototype_weather_model.joblib", nested)

    # Remove one final-test episode without changing any input or development row.
    changed_days = data["forecast_date"].between("2020-07-19", "2020-07-21")
    assert data.loc[changed_days, TARGET].sum() == 3
    data.loc[changed_days, TARGET] = 0
    data.loc[changed_days, "target_max_stage_ft"] = 3.0
    data.to_csv(path, index=False)
    changed_report = train(path, tmp_path / "second", "2020-03-01", "2020-05-01", 8)
    changed_predictions = pd.read_csv(tmp_path / "second/test_predictions.csv")
    assert report["selected_model"] == changed_report["selected_model"]
    assert report["decision_threshold"] == changed_report["decision_threshold"]
    assert report["validation_models"] == changed_report["validation_models"]
    assert report["validation_selected_threshold"] == changed_report["validation_selected_threshold"]
    assert report["training_input_ranges"] == changed_report["training_input_ranges"]
    assert report["dataset_sha256"] != changed_report["dataset_sha256"]
    np.testing.assert_allclose(saved["flood_stage_probability"], changed_predictions["flood_stage_probability"])
    np.testing.assert_array_equal(saved["predicted_flood_stage"], changed_predictions["predicted_flood_stage"])


def test_invalid_training_data_cannot_write_model_artifacts(labelled_weather, tmp_path):
    path = tmp_path / "incomplete.csv"
    labelled_weather.drop(columns="windKph").to_csv(path, index=False)
    output = tmp_path / "model"
    with pytest.raises(ValueError):
        train(path, output, "2020-03-01", "2020-05-01", 8)
    assert not output.exists()


def test_threshold_search_handles_rare_event_scores_below_fixed_grid():
    assert select_threshold(pd.Series([0, 1, 0, 1]), np.array([.001, .004, .002, .003])) == .003


def test_identical_scores_cannot_be_split_by_threshold():
    assert select_threshold(pd.Series([0, 1, 0, 1]), np.full(4, .001)) == .001
