"""Synthetic fixtures verify mechanics only; their scores are not flood-model evidence."""

from copy import deepcopy
import json

import httpx
import joblib
import numpy as np
import pandas as pd
import pytest
from threadpoolctl import threadpool_limits

from ai.area.data import (
    FEATURES, LABEL_COLUMNS, ROOT, TIMEZONE, VARIABLES, build_daily_features,
    download, read_areas,
)
from ai.area.train import INPUT_COLUMNS, prepare_training_data, score, temporal_split, train


@pytest.fixture
def hourly_payload():
    return {
        "timezone": TIMEZONE, "latitude": -17.75, "longitude": 177.42, "elevation": 15,
        "hourly_units": VARIABLES.copy(),
        "hourly": {
            "time": pd.date_range("2024-01-01", periods=49, freq="h").strftime("%Y-%m-%dT%H:%M").tolist(),
            "precipitation_previous_day2": [float(i) for i in range(49)],
            "temperature_2m_previous_day2": [25.0] * 49,
            "relative_humidity_2m_previous_day2": [80.0] * 49,
        },
    }


AREA = {"area_id": "nadi", "latitude": -17.7765, "longitude": 177.4356}


def test_daily_features_use_fiji_window_and_archived_forecast_bound(hourly_payload):
    frame, missing = build_daily_features(hourly_payload, AREA, "2024-01-01", "2024-01-02")
    assert missing == [] and len(frame) == 2
    row = frame.iloc[0]
    assert row["issued_at"] == "2023-12-31T12:00:00+00:00"
    assert row["window_end"] == "2024-01-01T12:00:00+00:00"
    assert row["latest_reference_time_bound"] == "2023-12-30T12:00:00+00:00"
    assert row["forecast_rain_mm_24h"] == sum(range(1, 25))
    assert row["forecast_rain_mm_6h_max"] == sum(range(19, 25))
    assert row["forecast_rain_mm_1h_max"] == 24
    assert row["forecast_temp_c_mean"] == 25
    assert row["latitude"] == AREA["latitude"]
    assert row["grid_latitude"] == -17.75


@pytest.mark.parametrize("problem", ["null", "missing_hour", "offset_hour"])
def test_incomplete_days_are_excluded_not_filled_with_zero(hourly_payload, problem):
    if problem == "null":
        hourly_payload["hourly"]["precipitation_previous_day2"][1] = None
    elif problem == "missing_hour":
        for values in hourly_payload["hourly"].values():
            del values[0]
    else:
        hourly_payload["hourly"]["time"][0] = "2024-01-01T00:30"
    frame, missing = build_daily_features(hourly_payload, AREA, "2024-01-01", "2024-01-02")
    assert frame["forecast_date"].tolist() == ["2024-01-02"]
    assert missing == ["2024-01-01"]


@pytest.mark.parametrize("problem", ["timezone", "units", "duplicate", "negative_rain", "humidity"])
def test_invalid_weather_contract_is_rejected(hourly_payload, problem):
    if problem == "timezone":
        hourly_payload["timezone"] = "UTC"
    elif problem == "units":
        hourly_payload["hourly_units"]["precipitation_previous_day2"] = "inch"
    elif problem == "duplicate":
        hourly_payload["hourly"]["time"][1] = hourly_payload["hourly"]["time"][0]
    elif problem == "negative_rain":
        hourly_payload["hourly"]["precipitation_previous_day2"][1] = -1
    else:
        hourly_payload["hourly"]["relative_humidity_2m_previous_day2"][0] = 101
    with pytest.raises(ValueError):
        build_daily_features(hourly_payload, AREA, "2024-01-01", "2024-01-02")


def test_last_day_requires_following_midnight_rainfall(hourly_payload):
    for values in hourly_payload["hourly"].values():
        values.pop()
    frame, missing = build_daily_features(hourly_payload, AREA, "2024-01-01", "2024-01-02")
    assert frame["forecast_date"].tolist() == ["2024-01-01"]
    assert missing == ["2024-01-02"]


def test_downloader_records_provenance_and_reuses_cache(hourly_payload, tmp_path, monkeypatch):
    areas = tmp_path / "areas.csv"
    pd.DataFrame([{**AREA, "name": "Nadi"}]).to_csv(areas, index=False)
    calls = []

    def get(client, url):
        calls.append(url)
        return httpx.Response(200, json=deepcopy(hourly_payload), request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", get)
    output = tmp_path / "data"
    report = download(areas, "2024-01-01", "2024-01-02", output)
    assert report["feature_rows"] == 2
    assert report["training_ready"] is False
    assert len(report["sources"][0]["raw_sha256"]) == 64
    labels = pd.read_csv(output / "labels_template.csv")
    assert labels["observed_flood"].isna().all()
    (output / "verified_labels.csv").write_text("researcher-owned file")
    download(areas, "2024-01-01", "2024-01-02", output)
    assert len(calls) == 1
    assert (output / "verified_labels.csv").read_text() == "researcher-owned file"
    changed = pd.read_csv(areas)
    changed["latitude"] = -17.8
    changed.to_csv(areas, index=False)
    with pytest.raises(ValueError, match="stale cache"):
        download(areas, "2024-01-01", "2024-01-02", output)


@pytest.fixture
def area_records(hourly_payload):
    template = build_daily_features(hourly_payload, AREA, "2024-01-01", "2024-01-01")[0].iloc[0].to_dict()
    features, labels = [], []
    for index, day in enumerate(pd.date_range("2024-01-01", periods=90, tz=TIMEZONE)):
        for area_index, area in enumerate(("nadi", "ba", "suva")):
            issue = day.tz_convert("UTC")
            outcome = int(index % 4 == 0)
            features.append({
                **template, "area_id": area, "forecast_date": day.date().isoformat(),
                "issued_at": issue.isoformat(), "window_end": (issue + pd.Timedelta(hours=24)).isoformat(),
                "latest_reference_time_bound": (issue - pd.Timedelta(hours=24)).isoformat(),
                "forecast_rain_mm_24h": float(index % 5 * 20 + area_index),
            })
            labels.append({
                "area_id": area, "forecast_date": day.date().isoformat(), "observed_flood": outcome,
                "label_source": "synthetic unit fixture; not a real observation",
                "event_id": f"fixture-{index}" if outcome else "",
                "coverage_note": "Synthetic complete coverage for software test only",
            })
    return pd.DataFrame(features), pd.DataFrame(labels)


def test_unknown_labels_are_excluded_and_annotations_cannot_shadow_features(area_records):
    features, labels = area_records
    labels["observed_flood"] = labels["observed_flood"].astype(float)
    labels.loc[0, "observed_flood"] = np.nan
    labels[FEATURES[0]] = "research note; not a predictor"
    joined = prepare_training_data(features, labels)
    assert len(joined) == len(features) - 1
    assert joined[FEATURES[0]].dtype.kind == "f"
    labels["observed_flood"] = np.nan
    with pytest.raises(ValueError, match="Blank labels are unknown"):
        prepare_training_data(features, labels)


@pytest.mark.parametrize("problem", ["missing_source", "missing_negative_coverage", "missing_event", "bad_target", "duplicate", "unmatched", "future_reference", "window", "minute", "missing_feature"])
def test_training_rejects_unverifiable_or_misaligned_data(area_records, problem):
    features, labels = area_records
    if problem == "missing_source":
        labels.loc[0, "label_source"] = " "
    elif problem == "missing_negative_coverage":
        labels.loc[3, "coverage_note"] = ""
    elif problem == "missing_event":
        labels.loc[0, "event_id"] = ""
    elif problem == "bad_target":
        labels.loc[0, "observed_flood"] = 2
    elif problem == "duplicate":
        labels = pd.concat([labels, labels.iloc[[0]]])
    elif problem == "unmatched":
        labels.loc[0, "area_id"] = "unmatched"
    elif problem == "future_reference":
        features.loc[0, "latest_reference_time_bound"] = "2024-01-02T00:00:00+00:00"
    elif problem == "window":
        features.loc[0, "window_end"] = features.loc[0, "issued_at"]
    elif problem == "minute":
        for column in ("issued_at", "window_end", "latest_reference_time_bound"):
            features.loc[0, column] = (pd.Timestamp(features.loc[0, column]) + pd.Timedelta(minutes=1)).isoformat()
    else:
        features.loc[0, FEATURES[0]] = np.nan
    with pytest.raises(ValueError):
        prepare_training_data(features, labels)


def test_time_splits_purge_dates_and_keep_geographic_holdout_out_of_training(area_records):
    data = prepare_training_data(*area_records)
    parts = temporal_split(data, "2024-02-01", "2024-03-01", holdout_areas=("suva",))
    assert parts["train"]["forecast_date"].max() == "2024-01-24"
    assert parts["validation"]["forecast_date"].min() == "2024-02-01"
    assert parts["validation"]["forecast_date"].max() == "2024-02-22"
    assert parts["test"]["forecast_date"].min() == "2024-03-01"
    for key in ("train", "validation", "test"):
        assert set(parts[key]["area_id"]) == {"nadi", "ba"}
    assert set(parts["unseen_area_test"]["area_id"]) == {"suva"}
    assert parts["unseen_area_test"]["forecast_date"].min() == "2024-03-01"


def test_shared_storm_across_splits_is_rejected(area_records):
    data = prepare_training_data(*area_records)
    data.loc[data["observed_flood"] == 1, "event_id"] = "same-storm"
    with pytest.raises(ValueError, match="Flood event crosses"):
        temporal_split(data, "2024-02-01", "2024-03-01")


def test_positive_only_catalog_cannot_train_classifier(area_records):
    data = prepare_training_data(*area_records)
    with pytest.raises(ValueError, match="flood and non-flood"):
        temporal_split(data[data["observed_flood"] == 1], "2024-02-01", "2024-03-01")


def test_per_area_metrics_support_single_class_without_inventing_auc():
    result = score(pd.Series([0, 0]), np.array([0.2, 0.8]), 0.5)
    assert result["roc_auc"] is None and result["average_precision"] is None
    assert result["confusion_matrix"] == [[1, 1], [0, 0]]
    json.dumps(result, allow_nan=False)


def test_training_artifact_and_model_selection_ignore_final_test_labels(area_records, tmp_path):
    features, labels = area_records
    feature_path, label_path = tmp_path / "features.csv", tmp_path / "labels.csv"
    features.to_csv(feature_path, index=False)
    labels.to_csv(label_path, index=False)
    with threadpool_limits(limits=1):
        report = train(feature_path, label_path, "2024-02-01", "2024-03-01", tmp_path / "first", holdout_areas=("suva",))
        bundle = joblib.load(tmp_path / "first" / "area_flood_model.joblib")
        saved = pd.read_csv(tmp_path / "first" / "test_predictions.csv")
        matching = saved.merge(features, on=["area_id", "forecast_date"], validate="one_to_one")
        np.testing.assert_allclose(saved["flood_probability"], bundle["pipeline"].predict_proba(matching[INPUT_COLUMNS])[:, 1])
        mask = labels["forecast_date"] >= "2024-03-01"
        labels.loc[mask, "observed_flood"] = 1 - labels.loc[mask, "observed_flood"]
        labels.loc[mask, "event_id"] = "changed-test-event"
        labels.to_csv(label_path, index=False)
        changed = train(feature_path, label_path, "2024-02-01", "2024-03-01", tmp_path / "second", holdout_areas=("suva",))
    assert report["selected_model"] == changed["selected_model"]
    assert report["decision_threshold"] == changed["decision_threshold"]
    assert report["validation_models"] == changed["validation_models"]
    assert report["development_only"] and not report["deployment_approved"]
    assert report["unseen_area_test"]["rows"] > 0
    assert report["test"]["rows"] == len(saved)
    json.dumps(report, allow_nan=False)


def test_blank_labels_stop_before_model_artifact_creation(area_records, tmp_path):
    features, labels = area_records
    labels["observed_flood"] = np.nan
    features.to_csv(tmp_path / "features.csv", index=False)
    labels.to_csv(tmp_path / "labels.csv", index=False)
    with pytest.raises(ValueError, match="No verified flood labels"):
        train(tmp_path / "features.csv", tmp_path / "labels.csv", "2024-02-01", "2024-03-01", tmp_path / "model")
    assert not (tmp_path / "model").exists()


def test_public_seed_labels_are_sourced_positives_for_existing_areas():
    areas = read_areas(ROOT / "areas.csv")
    labels = pd.read_csv(ROOT / "public_positive_labels.csv")
    assert set(LABEL_COLUMNS) <= set(labels)
    assert set(labels["area_id"]) <= set(areas["area_id"])
    assert not labels.duplicated(["area_id", "forecast_date"]).any()
    assert labels["observed_flood"].eq(1).all()
    assert labels["label_source"].str.startswith("https://www.met.gov.fj/").all()
    assert labels[["coverage_note", "event_id"]].notna().all().all()
