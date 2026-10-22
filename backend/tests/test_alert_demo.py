"""Explicitly simulated review scenarios must never bypass approval or demo opt-in."""

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.seed_locations import seed_demo_locations
from app.models import Alert, Prediction, UserRole


@pytest.fixture
def demo_setup(monkeypatch, db, user_factory):
    monkeypatch.setenv("ALERT_DEMO_ENABLED", "true")
    get_settings.cache_clear()
    seed_demo_locations(db)
    admin = user_factory(email="demo-reviewer@example.test", role=UserRole.MET_ADMIN)
    return {"Authorization": f"Bearer {create_access_token(admin.id)}"}


@pytest.mark.parametrize("scenario,severity,location", [
    ("nausori-high", "HIGH", "Nausori"), ("labasa-very-high", "VERY_HIGH", "Labasa"),
])
def test_demo_runs_through_persistent_prediction_pending_approval_and_suppression(client, db, demo_setup, scenario, severity, location):
    url = f"/api/admin/alerts/demo/{scenario}"
    result = client.post(url, headers=demo_setup)
    assert result.status_code == 200, result.text
    pending = result.json()
    assert pending["status"] == "PENDING"
    assert pending["severity"] == severity and pending["location"]["name"] == location
    assert pending["is_demo"] and pending["prediction"]["is_sample"]
    assert "DEMO ONLY" in pending["message"]
    assert db.get(Prediction, pending["prediction_id"]).is_alert_demo
    db.rollback()
    assert client.get("/api/alerts/active").json() == []
    assert client.post(url, headers=demo_setup).json()["id"] == pending["id"]
    assert db.scalar(select(func.count()).select_from(Alert)) == 1
    db.rollback()
    review = f"/api/admin/alerts/{pending['id']}"
    approved = client.patch(review + "/approve", headers=demo_setup)
    assert approved.status_code == 200
    assert approved.json()["approved_at"]
    public = client.get("/api/alerts/active").json()
    assert len(public) == 1 and public[0]["is_demo"]
    assert public[0]["prediction"]["is_sample"]
    assert "approved_by_user_id" not in public[0]
    assert client.post(url, headers=demo_setup).json()["id"] == pending["id"]
    assert client.patch(review + "/suppress", headers=demo_setup, json={"reason": ""}).status_code == 422
    assert client.patch(review + "/suppress", headers=demo_setup, json={"reason": "Review demo completed"}).status_code == 200
    assert client.get("/api/alerts/active").json() == []
    fresh = client.post(url, headers=demo_setup).json()
    assert fresh["id"] != pending["id"] and fresh["prediction_id"] != pending["prediction_id"]
    assert fresh["status"] == "PENDING"


def test_switching_off_demo_hides_approved_fixtures_and_prevents_creation_or_approval(client, demo_setup, monkeypatch):
    first = client.post("/api/admin/alerts/demo/nausori-high", headers=demo_setup).json()
    second = client.post("/api/admin/alerts/demo/labasa-very-high", headers=demo_setup).json()
    assert client.patch(f"/api/admin/alerts/{first['id']}/approve", headers=demo_setup).status_code == 200
    monkeypatch.setenv("ALERT_DEMO_ENABLED", "false")
    get_settings.cache_clear()
    assert client.get("/api/alerts/active").json() == []
    assert client.post("/api/admin/alerts/demo/nausori-high", headers=demo_setup).status_code == 404
    assert client.patch(f"/api/admin/alerts/{second['id']}/approve", headers=demo_setup).status_code == 400


def test_demo_requires_admin_and_known_scenario(client, demo_setup, user_factory):
    community = user_factory(email="demo-community@example.test")
    url = "/api/admin/alerts/demo/nausori-high"
    assert client.post(url).status_code == 401
    assert client.post(url, headers={"Authorization": "Bearer invalid"}).status_code == 401
    assert client.post(url, headers={"Authorization": f"Bearer {create_access_token(community.id)}"}).status_code == 403
    assert client.post("/api/admin/alerts/demo/unknown", headers=demo_setup).status_code == 400


def test_normal_map_samples_still_cannot_create_alerts_in_demo_mode(client, db, demo_setup):
    sample = db.scalar(select(Prediction).where(Prediction.model_version == "sample-demo-not-a-model-result"))
    sample_id = sample.id
    db.rollback()
    assert client.post(f"/api/admin/alerts/from-prediction/{sample_id}", headers=demo_setup).status_code == 400


def test_map_reseeding_does_not_overwrite_demo_prediction(client, db, demo_setup):
    pending = client.post("/api/admin/alerts/demo/nausori-high", headers=demo_setup).json()
    seed_demo_locations(db)
    db.expire_all()
    stored = db.get(Prediction, pending["prediction_id"])
    assert stored.is_alert_demo and stored.flood_probability == .82
    db.rollback()
    assert client.patch(f"/api/admin/alerts/{pending['id']}/approve", headers=demo_setup).status_code == 200
