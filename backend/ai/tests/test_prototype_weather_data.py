"""Synthetic hourly fixtures test time alignment, never model performance."""

from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from ai.prototype_weather.data import UNITS, build_weather_features
from ai.prototype_weather.schema import INPUT_COLUMNS


@pytest.fixture
def hourly_weather():
    times = pd.date_range("2025-01-01", periods=73, freq="h")
    return {
        "utc_offset_seconds": 0,
        "timezone": "GMT",
        "hourly_units": {"time": "iso8601", **UNITS},
        "hourly": {
            "time": times.strftime("%Y-%m-%dT%H:%M").tolist(),
            "rain": list(range(73)),
            "temperature_2m": [20 + index / 100 for index in range(73)],
            "relative_humidity_2m": [50 + index / 100 for index in range(73)],
            "wind_speed_10m": [10 + index / 100 for index in range(73)],
        },
    }


def build(payload, days=None):
    return build_weather_features(payload, 41.5, -91.5, days or ["2025-01-02"])


def test_rain_includes_exactly_24_preceding_hour_endpoints(hourly_weather):
    # The value at Jan1 00:00 describes Dec31 23:00–Jan1 00:00 and is excluded.
    hourly_weather["hourly"]["rain"][0] = 99999
    # Jan2 01:00 is the first target-day hour, also outside the input window.
    hourly_weather["hourly"]["rain"][25] = 99999
    rows, missing = build(hourly_weather)
    assert missing == []
    row = rows.iloc[0]
    assert row["rainfall24hMm"] == sum(range(1, 25))
    assert row["rain_window_start"] == "2025-01-01T00:00:00+00:00"
    assert row["weather_reference_at"] == "2025-01-02T00:00:00+00:00"
    assert row["forecast_date"] == "2025-01-02"
    assert row["weather_source_kind"] == "ERA5_REANALYSIS"
    assert row["latitude"] == 41.5
    assert row["longitude"] == -91.5


def test_temperature_humidity_and_wind_are_instantaneous_at_issue(hourly_weather):
    hourly = hourly_weather["hourly"]
    hourly["temperature_2m"][24] = 32.5
    hourly["relative_humidity_2m"][24] = 97
    hourly["wind_speed_10m"][24] = 4.5
    rows, _ = build(hourly_weather)
    assert rows.iloc[0]["temperatureC"] == 32.5
    assert rows.iloc[0]["humidityPercent"] == 97
    assert rows.iloc[0]["windKph"] == 4.5


def test_future_weather_cannot_change_prediction_inputs(hourly_weather):
    original, _ = build(hourly_weather)
    changed = deepcopy(hourly_weather)
    for field, value in {
        "rain": 900, "temperature_2m": 45,
        "relative_humidity_2m": 99, "wind_speed_10m": 75,
    }.items():
        changed["hourly"][field][25:] = [value] * 48
    new, _ = build(changed)
    pd.testing.assert_frame_equal(original[INPUT_COLUMNS], new[INPUT_COLUMNS])


@pytest.mark.parametrize("missing_index", [1, 12, 24])
def test_missing_rain_hour_excludes_only_affected_day(hourly_weather, missing_index):
    for values in hourly_weather["hourly"].values():
        values.pop(missing_index)
    rows, missing = build(hourly_weather, ["2025-01-02", "2025-01-03"])
    assert missing == ["2025-01-02"]
    assert rows["forecast_date"].tolist() == ["2025-01-03"]
    assert rows.iloc[0]["rainfall24hMm"] == sum(range(25, 49))


@pytest.mark.parametrize("field", ["rain", "temperature_2m", "relative_humidity_2m", "wind_speed_10m"])
@pytest.mark.parametrize("value", [None, np.nan, np.inf])
def test_missing_or_nonfinite_issue_measurement_excludes_day(hourly_weather, field, value):
    hourly_weather["hourly"][field][24] = value
    rows, missing = build(hourly_weather)
    assert rows.empty
    assert missing == ["2025-01-02"]


def test_missing_historical_rain_is_not_filled_with_zero(hourly_weather):
    hourly_weather["hourly"]["rain"][10] = None
    rows, missing = build(hourly_weather)
    assert rows.empty
    assert missing == ["2025-01-02"]


def test_missing_historical_instantaneous_weather_is_not_required(hourly_weather):
    for field in ("temperature_2m", "relative_humidity_2m", "wind_speed_10m"):
        hourly_weather["hourly"][field][10] = None
    rows, missing = build(hourly_weather)
    assert len(rows) == 1
    assert missing == []


@pytest.mark.parametrize("field,unit", [
    ("rain", "inch"), ("temperature_2m", "°F"),
    ("relative_humidity_2m", "fraction"), ("wind_speed_10m", "m/s"),
])
def test_wrong_units_are_rejected(hourly_weather, field, unit):
    hourly_weather["hourly_units"][field] = unit
    with pytest.raises(ValueError, match="units"):
        build(hourly_weather)


@pytest.mark.parametrize("field,value", [
    ("timezone", "Pacific/Fiji"), ("utc_offset_seconds", 43200),
])
def test_non_utc_weather_is_rejected(hourly_weather, field, value):
    hourly_weather[field] = value
    with pytest.raises(ValueError, match="UTC"):
        build(hourly_weather)


@pytest.mark.parametrize("problem", ["duplicate", "unordered"])
def test_duplicate_or_unordered_hours_are_rejected(hourly_weather, problem):
    times = hourly_weather["hourly"]["time"]
    if problem == "duplicate":
        times[12] = times[11]
    else:
        times[11], times[12] = times[12], times[11]
    with pytest.raises(ValueError, match="unique and ordered"):
        build(hourly_weather)


def test_negative_historical_rain_is_rejected_even_if_sum_would_be_positive(hourly_weather):
    hourly_weather["hourly"]["rain"][10] = -1
    with pytest.raises(ValueError, match="negative"):
        build(hourly_weather)
