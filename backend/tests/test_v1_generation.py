from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from app.db.import_v1_weather import import_window
from app.db.seed_locations import seed_demo_locations
from app.models import GeneratedPredictionProvenance, SyntheticAlert, SyntheticPrediction, V1WeatherProfile, UserRole
from app.models.weather import DemoWeatherObservation
from app.services import prediction_generation
from app.services.v1_features import RAW, GEO, DataUnavailable, feature_row
from app.services.v1_model import load_v1_model, V1ModelUnavailable

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "ml/data/synthetic_fiji/v1"
ARTIFACTS = ROOT / "ml/artifacts/synthetic/v1"
STAMP = pd.Timestamp("2024-07-10T00:00:00Z")
SOURCE = "generation-test-v1"


@pytest.fixture(scope="module")
def actual_model():
    if not (ARTIFACTS / "selected_model.joblib").exists():
        pytest.skip("Published V1 artifacts required")
    return load_v1_model(str(ARTIFACTS))


@pytest.fixture(scope="module")
def weather_window():
    if not DATASET.exists():
        pytest.skip("Original V1 dataset required for parity")
    return pd.read_parquet(DATASET / "weather_observations.parquet", filters=[
        ("timestamp", ">=", STAMP - pd.Timedelta(hours=174)), ("timestamp", "<=", STAMP)])


def test_actual_feature_and_pipeline_parity_all_locations(weather_window, actual_model):
    registry = pd.read_csv(DATASET / "locations.csv").set_index("location_id")
    saved = pd.read_parquet(ARTIFACTS / "features.parquet", filters=[("timestamp", "==", STAMP)]).set_index("location_id")
    for location_id, group in weather_window.groupby("location_id"):
        features = feature_row(group.sort_values("timestamp")[["timestamp", *RAW]], registry.loc[location_id].to_dict(), actual_model.features)
        np.testing.assert_allclose(features.to_numpy(dtype=float), saved.loc[[location_id], actual_model.features].to_numpy(dtype=float), atol=1e-10, rtol=1e-12, equal_nan=True)
        expected = actual_model.bundle["model"].predict_proba(saved.loc[[location_id], actual_model.features])[0, 1]
        assert actual_model.predict(features)[0] == pytest.approx(expected, abs=1e-12)


def test_missingness_policy_and_history_guards(actual_model):
    dates = pd.date_range("2024-01-01", periods=175, freq="h", tz="UTC")
    frame = pd.DataFrame({"timestamp": dates, **{name: np.ones(175) for name in RAW}})
    # Six past-only forward fills, then NaN; preserve original missing indicator.
    frame.loc[167:, "rainfall_mm"] = np.nan
    attributes = dict.fromkeys(GEO, 1.0)
    row = feature_row(frame, attributes, actual_model.features)
    assert pd.isna(row.rainfall_mm.iloc[0]) and row.rainfall_mm_missing.iloc[0] == 1
    assert row.rainfall_mm_total_3h.iloc[0] == 1.0
    with pytest.raises(DataUnavailable, match="static"):
        feature_row(frame, {key: value for key, value in attributes.items() if key != "elevation_m"}, actual_model.features)
    with pytest.raises(DataUnavailable, match="175"):
        feature_row(frame.iloc[1:], attributes, actual_model.features)
    frame["coastal_tide_m"] = np.nan
    with pytest.raises(DataUnavailable, match="sensor"):
        feature_row(frame, attributes, actual_model.features)


@pytest.fixture
def generated_setup(db, client, user_factory, monkeypatch, actual_model, weather_window):
    seed_demo_locations(db)
    import_window(db, DATASET, STAMP, SOURCE)
    user_factory(email="generator@example.com", role=UserRole.MET_ADMIN)
    token = client.post("/api/auth/login", json={"email": "generator@example.com", "password": "Password123!"}).json()["access_token"]
    monkeypatch.setenv("SYNTHETIC_DEMO_ENABLED", "true")
    get_settings.cache_clear()
    return {"Authorization": f"Bearer {token}"}


def request(location_id=1, **changes):
    return {"location_id": location_id, "timestamp": STAMP.isoformat(), "source": SOURCE,
            "source_type": "synthetic", "research_mode": True, "historical_replay": True, **changes}


def test_generated_api_all_locations_and_duplicates(client, db, generated_setup):
    for location_id in range(1, 13):
        first = client.post("/api/predictions/generate", json=request(location_id), headers=generated_setup)
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["status"] == "OK", body
        assert body["source_type"] == "synthetic" and body["research_mode"]
        assert body["horizon_hours"] == 24 and body["input_sha256"]
        if body["risk_category"] in ("HIGH", "VERY_HIGH"):
            assert body["alert_status"] == "PENDING"
        else:
            assert body["alert_id"] is None
        again = client.post("/api/predictions/generate", json=request(location_id), headers=generated_setup).json()
        assert again["prediction_id"] == body["prediction_id"] and again["alert_id"] == body["alert_id"]
    assert db.scalar(select(func.count()).select_from(SyntheticPrediction)) == 12
    db.commit()
    assert client.get("/api/alerts/active").json() == []
    assert client.get("/api/risk/suva").status_code == 410


def test_invalid_source_stale_missing_profile_units_and_future(client, db, generated_setup):
    for changes, reason in [({"research_mode": False}, "research-only"),
                            ({"source_type": "manual"}, "Genuine"),
                            ({"historical_replay": False}, "stale"),
                            ({"source": "unknown"}, "profile")]:
        body = client.post("/api/predictions/generate", json=request(**changes), headers=generated_setup).json()
        assert body["status"] == "DATA_UNAVAILABLE" and reason in body["reason"]
    assert client.post("/api/predictions/generate", json=request(timestamp="2099-01-01T00:00:00Z"), headers=generated_setup).status_code == 422
    assert client.post("/api/predictions/generate", json=request()).status_code == 401
    row = db.scalar(select(DemoWeatherObservation).where(DemoWeatherObservation.location_id == 1, DemoWeatherObservation.rainfall_mm.is_not(None)))
    row.rainfall_period_minutes = 1440
    db.commit()
    body = client.post("/api/predictions/generate", json=request(), headers=generated_setup).json()
    assert body["status"] == "DATA_UNAVAILABLE" and "60-minute" in body["reason"]
    assert db.scalar(select(func.count()).select_from(SyntheticPrediction)) == 0


def test_model_failure_and_alert_failure_roll_back(client, db, generated_setup, monkeypatch, actual_model):
    def fail_model(_):
        raise V1ModelUnavailable("Injected model failure")
    with monkeypatch.context() as patch:
        patch.setattr(actual_model, "predict", fail_model)
        assert client.post("/api/predictions/generate", json=request(), headers=generated_setup).status_code == 503
    assert db.scalar(select(func.count()).select_from(SyntheticPrediction)) == 0
    db.commit()
    def fail_alert(*args, **kwargs):
        raise OperationalError("injected", {}, Exception("private"))
    monkeypatch.setattr(prediction_generation, "create_alert_from_prediction", fail_alert)
    response = client.post("/api/predictions/generate", json=request(), headers=generated_setup)
    assert response.status_code == 503 and "private" not in response.text
    assert db.scalar(select(func.count()).select_from(SyntheticPrediction)) == 0
    assert db.scalar(select(func.count()).select_from(GeneratedPredictionProvenance)) == 0
    assert db.scalar(select(func.count()).select_from(SyntheticAlert)) == 0


def test_static_datum_coverage_and_future_isolation(client, db, generated_setup):
    profile = db.get(V1WeatherProfile, (SOURCE, 1))
    original = dict(profile.attributes)
    profile.attributes = {key: value for key, value in original.items() if key != "elevation_m"}
    db.commit()
    response = client.post("/api/predictions/generate", json=request(), headers=generated_setup).json()
    assert response["status"] == "DATA_UNAVAILABLE" and "elevation_m" in response["reason"]
    profile.attributes = original
    last = db.scalar(select(DemoWeatherObservation).where(DemoWeatherObservation.location_id == 1).order_by(DemoWeatherObservation.observed_at.desc()))
    datum = last.gauge_datum
    last.gauge_datum = "unknown-gauge"
    db.commit()
    response = client.post("/api/predictions/generate", json=request(), headers=generated_setup).json()
    assert response["status"] == "DATA_UNAVAILABLE" and "datum" in response["reason"]
    last.gauge_datum = datum
    db.commit()
    before = client.post("/api/predictions/generate", json=request(), headers=generated_setup).json()
    assert before["status"] == "OK"
    values = {column.name: getattr(last, column.name) for column in DemoWeatherObservation.__table__.columns if column.name != "id"}
    values.update(observed_at=(STAMP + pd.Timedelta(hours=1)).to_pydatetime(), rainfall_mm=4000)
    db.add(DemoWeatherObservation(**values))
    db.commit()
    after = client.post("/api/predictions/generate", json=request(), headers=generated_setup).json()
    assert before["input_sha256"] == after["input_sha256"] and before["probability"] == after["probability"]
    # Existing predictions are immutable if their input history is subsequently changed.
    last.temperature_c = 20.12345
    db.commit()
    assert client.post("/api/predictions/generate", json=request(), headers=generated_setup).status_code == 409
    db.delete(last)
    db.commit()
    response = client.post("/api/predictions/generate", json=request(), headers=generated_setup).json()
    assert response["status"] == "DATA_UNAVAILABLE" and "history" in response["reason"]


def test_gates_and_community_authorization(client, db, generated_setup, user_factory, monkeypatch):
    user_factory(email="reader-generation@example.com")
    token = client.post("/api/auth/login", json={"email": "reader-generation@example.com", "password": "Password123!"}).json()["access_token"]
    assert client.post("/api/predictions/generate", json=request(), headers={"Authorization": f"Bearer {token}"}).status_code == 403
    monkeypatch.setenv("SYNTHETIC_DEMO_ENABLED", "false")
    get_settings.cache_clear()
    body = client.post("/api/predictions/generate", json=request(), headers=generated_setup).json()
    assert body["status"] == "OK" and body["alert_id"] is None


def test_model_checksum_failure(tmp_path, actual_model):
    import json
    (tmp_path / "model_metadata.json").write_text(json.dumps(actual_model.metadata))
    (tmp_path / "selected_model.joblib").write_bytes(b"corrupted-bundle")
    with pytest.raises(V1ModelUnavailable):
        load_v1_model(str(tmp_path))


def test_synthetic_approval_never_reaches_operational_public_feed(client, db, generated_setup, actual_model):
    from app.models import Alert
    saved = pd.read_parquet(ARTIFACTS / "features.parquet", filters=[
        ("timestamp", ">=", pd.Timestamp("2024-07-01", tz="UTC")),
        ("timestamp", "<", pd.Timestamp("2024-08-01", tz="UTC"))],
        columns=["timestamp", "location_id", *actual_model.features])
    probabilities = actual_model.bundle["model"].predict_proba(saved[actual_model.features])[:, 1]
    eligible = np.flatnonzero(probabilities >= actual_model.bundle["threshold"])
    assert len(eligible) > 0, "V1 dataset must contain an eligible HIGH/VERY_HIGH window"
    row = saved.iloc[eligible[0]]
    timestamp, location_id = pd.Timestamp(row.timestamp), int(row.location_id)
    import_window(db, DATASET, timestamp, SOURCE)
    body = client.post("/api/predictions/generate",
                       json=request(location_id, timestamp=timestamp.isoformat()), headers=generated_setup).json()
    assert body["status"] == "OK", body
    assert body["alert_id"] is not None and body["alert_status"] == "PENDING"
    approved = client.post(f"/api/synthetic/admin/alerts/{body['alert_id']}/approve", headers=generated_setup)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["source_type"] == "synthetic"
    # The isolated approval keeps the operational alert table and public feed untouched.
    assert db.scalar(select(func.count()).select_from(SyntheticAlert)) == 1
    assert db.scalar(select(func.count()).select_from(Alert)) == 0
    db.commit()
    assert client.get("/api/alerts/active").json() == []
    assert client.get("/api/synthetic/alerts").json()[0]["source_type"] == "synthetic"
