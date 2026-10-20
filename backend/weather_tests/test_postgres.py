"""Opt-in real PostgreSQL tests in a disposable schema on configured DATABASE_URL.

Run from backend: WEATHER_POSTGRES_TEST=1 .venv/bin/python -m pytest weather_tests -q
"""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app import models
from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db import session as sessions
from app.db.seed_locations import seed_demo_locations
from app.main import app
from app.models.weather import WeatherObservation
from app.schemas.weather import WeatherCreate
from app.services.weather_service import insert_observation

pytestmark = pytest.mark.skipif(os.getenv("WEATHER_POSTGRES_TEST") != "1", reason="Opt in with WEATHER_POSTGRES_TEST=1")


@pytest.fixture
def postgres(monkeypatch):
    url = get_settings().database_url
    admin_engine = create_engine(url)
    schema = "weather_test_" + uuid4().hex
    with admin_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        # Existing operational baseline is create_all; both versioned migrations are real.
        tables = [table for table in Base.metadata.sorted_tables
                  if not table.name.startswith(("synthetic_", "weather_", "demo_weather_", "v1_weather_", "generated_prediction_", "notification_", "saved_locations"))]
        Base.metadata.create_all(engine, tables=tables)
        # create_all builds operational tables at their current shape, so remove
        # columns added by later ordered migrations before replaying them.
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE alerts DROP COLUMN expires_at"))
        monkeypatch.setattr(sessions, "get_engine", lambda: engine)
        command.upgrade(Config("alembic.ini"), "head")
        factory = sessionmaker(engine, expire_on_commit=False)
        with factory() as db:
            seed_demo_locations(db)
            user = models.User(name="Weather Test", email="weather-test@example.invalid", hashed_password="unused",
                               role=models.UserRole.MET_ADMIN, status=models.AccountStatus.APPROVED, is_active=True)
            db.add(user)
            db.commit()
            token = create_access_token(user.id)
        def database():
            with factory() as db:
                yield db
        app.dependency_overrides[sessions.get_db] = database
        yield engine, factory, {"Authorization": f"Bearer {token}"}
        command.downgrade(Config("alembic.ini"), "20261019_synthetic")
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        with admin_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


def test_postgres_api_persistence_all_locations(postgres):
    engine, factory, headers = postgres
    with factory() as db:
        ids = list(db.scalars(select(models.Location.id)))
    assert len(ids) == 12
    with TestClient(app) as client:
        for location_id in ids:
            data = {"location_id": location_id, "observed_at": "2026-01-01T12:00:00+12:00",
                    "source": "isolated-test-gauge", "temperature_c": 27}
            result = client.post("/api/admin/weather/observations", json=data, headers=headers)
            assert result.status_code == 201, result.text
            assert client.post("/api/admin/weather/observations", json=data, headers=headers).status_code == 200
    engine.dispose()  # A new connection/client can still retrieve committed measurements.
    with TestClient(app) as client:
        for location_id in ids:
            result = client.get(f"/api/weather/latest?location_id={location_id}")
            assert result.json()["observation"]["temperature_c"] == 27
            assert result.json()["observation"]["observed_at"] == "2026-01-01T00:00:00Z"
            assert client.get(f"/api/weather/latest?location_id={location_id}&dataset=synthetic").json()["status"] == "no_data"
    with factory() as db:
        assert len(list(db.scalars(select(WeatherObservation)))) == 12


def test_postgres_concurrent_identity_and_source_constraint(postgres):
    _, factory, _ = postgres
    with factory() as db:
        location_id = db.scalar(select(models.Location.id))
    data = WeatherCreate(location_id=location_id, observed_at=datetime.now(timezone.utc), source="race-test", humidity_pct=80)
    def write(_):
        with factory() as db:
            row, created = insert_observation(db, data)
            db.commit()
            return row.id, created
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(write, range(4)))
    assert len({row_id for row_id, _ in results}) == 1
    assert sum(created for _, created in results) == 1
    with factory() as db:
        db.add(WeatherObservation(**data.model_copy(update={"source_type": "synthetic"}).model_dump(),
                                  received_at=datetime.now(timezone.utc)))
        with pytest.raises(IntegrityError):
            db.commit()
