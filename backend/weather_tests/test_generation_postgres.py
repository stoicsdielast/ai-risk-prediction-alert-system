"""Actual V1 -> weather rows -> feature builder -> PostgreSQL -> pending demo alert."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from weather_tests.test_postgres import postgres, pytestmark  # noqa: F401
from app.core.config import get_settings
from app.db.import_v1_weather import import_window
from app.main import app
from app.models import Alert, GeneratedPredictionProvenance, SyntheticAlert, SyntheticPrediction
from app.services.v1_model import load_v1_model

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "postgres-v1-inference-test"


@pytest.fixture(scope="module")
def high_case():
    directory = ROOT / "ml/artifacts/synthetic/v1"
    dataset = ROOT / "ml/data/synthetic_fiji/v1"
    if not (directory / "features.parquet").exists() or not dataset.exists():
        pytest.skip("Original V1 artifacts and dataset required")
    model = load_v1_model(str(directory))
    # Scenario selection for TEST coverage, never used by the prediction service.
    rows = pd.read_parquet(directory / "features.parquet", filters=[
        ("timestamp", ">=", pd.Timestamp("2024-07-01", tz="UTC")),
        ("timestamp", "<", pd.Timestamp("2024-08-01", tz="UTC"))])
    probabilities = model.bundle["model"].predict_proba(rows[model.features])[:, 1]
    chosen = rows.iloc[np.flatnonzero(probabilities >= model.bundle["threshold"])[0]]
    return chosen.timestamp, int(chosen.location_id), model


@pytest.fixture
def ready(postgres, high_case, monkeypatch):
    engine, factory, headers = postgres
    timestamp, location_id, model = high_case
    monkeypatch.setenv("SYNTHETIC_DEMO_ENABLED", "true")
    get_settings.cache_clear()
    with factory() as db:
        import_window(db, ROOT / "ml/data/synthetic_fiji/v1", timestamp, SOURCE)
    yield engine, factory, headers, timestamp, location_id, model
    get_settings.cache_clear()


def body(timestamp, location_id):
    return {"location_id": location_id, "timestamp": timestamp.isoformat(), "source": SOURCE,
            "source_type": "synthetic", "research_mode": True, "historical_replay": True}


def test_actual_postgres_all_locations_and_concurrent_alert(ready):
    engine, factory, headers, timestamp, high_location, model = ready
    with TestClient(app) as client:
        def generate(_):
            response = client.post("/api/predictions/generate", json=body(timestamp, high_location), headers=headers)
            assert response.status_code == 200, response.text
            return response.json()
        with ThreadPoolExecutor(max_workers=3) as workers:
            concurrent = list(workers.map(generate, range(3)))
        assert len({item["prediction_id"] for item in concurrent}) == 1
        assert len({item["alert_id"] for item in concurrent}) == 1
        assert concurrent[0]["alert_status"] == "PENDING"
        assert concurrent[0]["risk_category"] in ("HIGH", "VERY_HIGH")
        saved_rows = pd.read_parquet(ROOT / "ml/artifacts/synthetic/v1/features.parquet",
                                     filters=[("timestamp", "==", timestamp)]).set_index("location_id")
        for location_id in range(1, 13):
            response = client.post("/api/predictions/generate", json=body(timestamp, location_id), headers=headers)
            assert response.status_code == 200, response.text
            result = response.json()
            assert result["status"] == "OK", result
            expected = model.predict(saved_rows.loc[[location_id], model.features])[0]
            assert result["probability"] == pytest.approx(expected, abs=1e-12)
        assert client.get("/api/alerts/active").json() == []
        assert client.get("/api/synthetic/alerts").json() == []  # Nothing auto-approved.
    engine.dispose()
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SyntheticPrediction)) == 12
        assert db.scalar(select(func.count()).select_from(GeneratedPredictionProvenance)) == 12
        assert db.scalar(select(func.count()).select_from(Alert)) == 0
        pending = db.get(SyntheticAlert, concurrent[0]["alert_id"])
        assert pending.status == "PENDING"
        pending.status = "REJECTED"
        db.commit()
    with TestClient(app) as client:
        again = client.post("/api/predictions/generate", json=body(timestamp, high_location), headers=headers).json()
        assert again["alert_status"] == "REJECTED"  # Retries never revive a reviewed row.
    print(f"Verified real V1 at {timestamp}: all 12 locations; high location={high_location}; concurrent retries share pending alert")


def test_postgres_alert_insert_failure_rolls_back_prediction(ready):
    engine, factory, headers, timestamp, high_location, _ = ready
    def reject_alert(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO synthetic_alerts"):
            # Force a real PostgreSQL statement failure in the active transaction.
            conn.exec_driver_sql("SELECT 1/0")
    event.listen(engine, "before_cursor_execute", reject_alert)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post("/api/predictions/generate", json=body(timestamp, high_location), headers=headers)
            assert response.status_code == 503
    finally:
        event.remove(engine, "before_cursor_execute", reject_alert)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SyntheticPrediction)) == 0
        assert db.scalar(select(func.count()).select_from(GeneratedPredictionProvenance)) == 0
        assert db.scalar(select(func.count()).select_from(SyntheticAlert)) == 0
