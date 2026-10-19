"""Synthetic fixtures verify the POC; only real archived records yield its report."""

import json

import joblib
import numpy as np
import pandas as pd
import pytest

from ai.river.data import FEATURES, INPUT_COLUMNS, build_area_dataset, daily_observations, extract_observations, read_sites, ROOT
from ai.river.predict import predict
from ai.river.train import TARGET, split_dataset, train, validate_dataset


def fixture_site(area="fixture-town", threshold=7.0):
    return {"area_id": area, "river_system": "fixture-river", "usgs_id": "01234567", "flood_stage_ft": threshold, "threshold_source": "https://example.org/synthetic-unit-fixture"}


def observation_payload():
    times = pd.date_range("2020-01-01", periods=96, freq="15min", tz="UTC")
    return {"value": {"timeSeries": [{
        "sourceInfo": {"siteCode": [{"value": "01234567"}]},
        "variable": {"variableCode": [{"value": "00065"}], "unit": {"unitCode": "ft"}, "noDataValue": -999999.0},
        "values": [{"value": [{"dateTime": time.isoformat(), "value": "6.0", "qualifiers": ["A"]} for time in times]}],
    }]}}


@pytest.mark.parametrize("problem", ["provisional", "estimated", "missing", "nodata"])
def test_unobserved_slots_never_become_nonflood_days(problem):
    payload = observation_payload()
    values = payload["value"]["timeSeries"][0]["values"][0]["value"]
    if problem == "provisional":
        values[0]["qualifiers"] = ["P"]
    elif problem == "estimated":
        values[0]["qualifiers"] = ["A", "e"]
    elif problem == "missing":
        values.pop()
    else:
        values[0]["value"] = "-999999.0"
    daily = daily_observations(extract_observations(payload, "01234567"), "2020-01-01", "2020-01-01")
    assert not daily.iloc[0]["complete"]
    assert pd.isna(daily.iloc[0]["max"])


def test_complete_observations_use_utc_and_preserve_actual_peak():
    payload = observation_payload()
    values = payload["value"]["timeSeries"][0]["values"][0]["value"]
    values[0]["dateTime"] = "2019-12-31T19:00:00-05:00"
    values[12]["value"] = "7.25"
    daily = daily_observations(extract_observations(payload, "01234567"), "2020-01-01", "2020-01-01")
    assert daily.iloc[0]["complete"]
    assert daily.iloc[0]["count"] == 96
    assert daily.iloc[0]["max"] == 7.25


@pytest.mark.parametrize("problem", ["wrong_site", "wrong_unit", "duplicate"])
def test_observation_source_contract_is_enforced(problem):
    payload = observation_payload()
    series = payload["value"]["timeSeries"][0]
    if problem == "wrong_site":
        series["sourceInfo"]["siteCode"][0]["value"] = "different"
    elif problem == "wrong_unit":
        series["variable"]["unit"]["unitCode"] = "m"
    else:
        series["values"][0]["value"].append(series["values"][0]["value"][0].copy())
    with pytest.raises(ValueError):
        extract_observations(payload, "01234567")


@pytest.fixture
def daily_fixture():
    index = pd.date_range("2020-01-01", periods=240, tz="UTC")
    maximum = np.where(np.arange(240) % 20 < 3, 8.0, 3.0)
    return pd.DataFrame({"count": 96, "max": maximum, "min": maximum - 1, "mean": maximum - 0.5, "complete": True}, index=index)


def test_future_target_measurement_is_never_a_feature(daily_fixture):
    original = build_area_dataset(daily_fixture, fixture_site())
    day = "2020-02-05"
    changed_daily = daily_fixture.copy()
    changed_daily.loc[day, "max"] = 50
    changed = build_area_dataset(changed_daily, fixture_site())
    old_row = original[original.forecast_date == day].iloc[0]
    new_row = changed[changed.forecast_date == day].iloc[0]
    np.testing.assert_allclose(old_row[FEATURES].to_numpy(float), new_row[FEATURES].to_numpy(float))
    assert old_row[TARGET] == 0 and new_row[TARGET] == 1
    assert new_row["last_input_observed_at"] == "2020-02-03T23:45:00+00:00"
    assert new_row["margin_lag2_ft"] == daily_fixture.loc["2020-02-03", "max"] - 7


def test_calendar_gap_is_not_compressed_or_interpolated(daily_fixture):
    daily_fixture.loc["2020-02-01", ["max", "min", "mean"]] = np.nan
    daily_fixture.loc["2020-02-01", "complete"] = False
    daily_fixture.loc["2020-02-01", "count"] = 95
    data = build_area_dataset(daily_fixture, fixture_site())
    dates = set(data.forecast_date)
    assert "2020-02-01" not in dates
    assert "2020-02-02" in dates  # last input is Jan31, so the Feb1 gap is irrelevant
    assert all(f"2020-02-{day:02}" not in dates for day in range(3, 10))
    assert "2020-02-10" in dates


@pytest.mark.parametrize("problem", ["target", "cutoff", "missing", "coverage", "duplicate"])
def test_invalid_training_rows_rejected(daily_fixture, problem):
    data = build_area_dataset(daily_fixture, fixture_site())
    if problem == "target":
        data.loc[0, TARGET] = 1 - data.loc[0, TARGET]
    elif problem == "cutoff":
        data.loc[0, "last_input_observed_at"] = data.loc[0, "issued_at"]
    elif problem == "missing":
        data.loc[0, FEATURES[0]] = np.nan
    elif problem == "coverage":
        data.loc[0, "approved_samples"] = 95
    else:
        data = pd.concat([data, data.iloc[[0]]])
    with pytest.raises(ValueError):
        validate_dataset(data)


def test_time_splits_keep_gap_and_both_classes(daily_fixture):
    data = build_area_dataset(daily_fixture, fixture_site())
    parts = split_dataset(data, "2020-03-01", "2020-05-01", 8)
    assert parts["train"].forecast_date.max() == "2020-02-21"
    assert parts["validation"].forecast_date.min() == "2020-03-01"
    assert parts["validation"].forecast_date.max() == "2020-04-22"
    assert parts["test"].forecast_date.min() == "2020-05-01"
    assert all(part[TARGET].nunique() == 2 for part in parts.values())


def test_long_flood_episode_cannot_cross_train_validation(daily_fixture):
    daily_fixture.loc["2020-02-15":"2020-03-05", "max"] = 8
    data = build_area_dataset(daily_fixture, fixture_site())
    with pytest.raises(ValueError, match="episode crosses"):
        split_dataset(data, "2020-03-01", "2020-05-01", 8)


def test_saved_model_predictions_and_selection_ignore_test_targets(daily_fixture, tmp_path):
    data = build_area_dataset(daily_fixture, fixture_site())
    path = tmp_path / "dataset.csv"
    data.to_csv(path, index=False)
    report = train(path, tmp_path / "first", "2020-03-01", "2020-05-01", 8)
    bundle = joblib.load(tmp_path / "first" / "river_flood_model.joblib")
    assert bundle["pipeline"].feature_names_in_.tolist() == INPUT_COLUMNS
    saved = pd.read_csv(tmp_path / "first" / "test_predictions.csv")
    matching = saved.merge(data, on=["area_id", "forecast_date"], suffixes=("_saved", ""))
    np.testing.assert_allclose(saved.flood_stage_probability, bundle["pipeline"].predict_proba(matching[INPUT_COLUMNS])[:, 1])
    example = predict(tmp_path / "first" / "river_flood_model.joblib", path)
    assert example["historical_demo"] and not example["fiji_validated"]
    assert example["areas_without_complete_data"] == []
    assert len(example["predictions"]) == 1
    assert not report["deployment_approved"] and not report["fiji_validated"]
    # Change a complete final-test episode while leaving every predictor untouched.
    mask = data.forecast_date.between("2020-07-19", "2020-07-21")
    data.loc[mask, TARGET] = 0
    data.loc[mask, "target_max_stage_ft"] = 3
    data.to_csv(path, index=False)
    changed = train(path, tmp_path / "second", "2020-03-01", "2020-05-01", 8)
    assert report["selected_model"] == changed["selected_model"]
    assert report["decision_threshold"] == changed["decision_threshold"]
    assert report["validation_models"] == changed["validation_models"]
    json.dumps(report, allow_nan=False)


def test_configured_sites_preserve_usgs_leading_zeros():
    sites = read_sites(ROOT / "sites.csv")
    assert "01389500" in sites.usgs_id.to_list()
    assert sites.area_id.nunique() == 4
