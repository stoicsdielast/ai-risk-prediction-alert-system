from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import get_settings
from app.models.location import Location
from app.models.user import UserRole
from app.models.weather import DemoWeatherObservation, WeatherObservation
from app.schemas.weather import WeatherCreate
from app.services.weather_ingestion import run_once


@pytest.fixture
def location(db):
    from app.db.seed_locations import seed_demo_locations
    seed_demo_locations(db)
    row = db.scalar(select(Location).order_by(Location.id))
    db.commit()
    return row


@pytest.fixture
def headers(client, user_factory):
    user_factory(email="weather@example.com", role=UserRole.MET_ADMIN)
    response = client.post("/api/auth/login", json={"email": "weather@example.com", "password": "Password123!"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def payload(location, **kwargs):
    return {"location_id": location.id, "observed_at": datetime.now(timezone.utc).isoformat(),
            "source": "test-gauge", "rainfall_mm": 12, "rainfall_period_minutes": 60, **kwargs}


def test_insert_retry_conflict_and_separation(client, db, location, headers):
    data = payload(location)
    response = client.post("/api/admin/weather/observations", json=data, headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["missing_fields"] and not response.json()["stale"]
    assert client.post("/api/admin/weather/observations", json=data, headers=headers).status_code == 200
    assert client.post("/api/admin/weather/observations", json={**data, "rainfall_mm": 13}, headers=headers).status_code == 409
    response = client.post("/api/admin/weather/observations", json={**data, "source_type": "synthetic"}, headers=headers)
    assert response.status_code == 201 and response.json()["notice"]
    assert db.scalar(select(WeatherObservation)).source_type == "manual"
    assert db.scalar(select(DemoWeatherObservation)).source_type == "synthetic"
    db.commit()
    assert client.get(f"/api/weather/latest?location_id={location.id}").json()["observation"]["source_type"] == "manual"
    assert client.get(f"/api/weather/latest?location_id={location.id}&dataset=synthetic").json()["notice"]


def test_ordering_history_no_data(client, location, headers, db):
    for hours in [1, 5]:
        data = payload(location, observed_at=(datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat())
        assert client.post("/api/admin/weather/observations", json=data, headers=headers).status_code == 201
    result = client.get(f"/api/weather/latest?location_id={location.id}").json()
    assert result["status"] == "fresh"
    history = client.get(f"/api/weather/observations?location_id={location.id}").json()["observations"]
    assert len(history) == 2 and history[1]["stale"]
    assert len(client.get(f"/api/weather/observations?location_id={location.id}&limit=1&offset=1").json()["observations"]) == 1
    others = list(db.scalars(select(Location).where(Location.id != location.id)))
    db.commit()
    for other in others:
        assert client.get(f"/api/weather/latest?location_id={other.id}").json()["status"] == "no_data"
    assert client.get("/api/weather/latest?location_id=999999").status_code == 404
    assert client.get(f"/api/weather/observations?location_id={location.id}&start=2025-01-01").status_code == 422


@pytest.mark.parametrize("change", [
    {"humidity_pct": 101}, {"temperature_c": 80}, {"rainfall_mm": -1},
    {"rainfall_period_minutes": None}, {"pressure_hpa": 0}, {"wind_speed_mps": -1},
    {"soil_moisture_pct": 101}, {"wind_direction_deg": 360},
    {"observed_at": "2020-01-01T00:00:00"}, {"observed_at": "2099-01-01T00:00:00Z"},
    {"units": "inches"}, {"source_type": "official"}, {"temperature_c": float("inf")},
])
def test_validation(location, change):
    with pytest.raises(ValidationError):
        WeatherCreate.model_validate(payload(location, **change))


def test_authorization_and_location(client, db, location, headers, user_factory):
    data = payload(location)
    assert client.post("/api/admin/weather/observations", json=data).status_code == 401
    user_factory(email="community-weather@example.com")
    token = client.post("/api/auth/login", json={"email": "community-weather@example.com", "password": "Password123!"}).json()["access_token"]
    assert client.post("/api/admin/weather/observations", json=data, headers={"Authorization": f"Bearer {token}"}).status_code == 403
    assert client.post("/api/admin/weather/observations", json={**data, "location_id": 999999}, headers=headers).status_code == 404
    location.is_active = False
    db.commit()
    assert client.post("/api/admin/weather/observations", json=data, headers=headers).status_code == 409


def test_scheduler_retries_atomicity_freshness(session_factory, location):
    settings = get_settings().model_copy(update={"weather_ingestion_enabled": True})
    calls = []
    def feed(_):
        calls.append(1)
        if len(calls) == 1:
            raise TimeoutError()
        return [WeatherCreate.model_validate(payload(location, source_type="synthetic"))]
    result = run_once(settings, session_factory, feed, sleep=lambda _: None)
    assert result["status"] == "ok" and result["created"] == 1 and len(calls) == 2
    assert result["stale_location_ids"]
    def bad_feed(_):
        return [WeatherCreate.model_validate(payload(location)),
                WeatherCreate.model_validate(payload(location, location_id=999999))]
    assert run_once(settings, session_factory, bad_feed, sleep=lambda _: None)["status"] == "failed"
    with session_factory() as db:
        assert db.scalar(select(WeatherObservation)) is None
