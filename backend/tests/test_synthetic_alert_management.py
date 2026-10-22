"""Explicit low-risk tests stay synthetic; lifecycle audit never enters public warnings."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.api.routes.synthetic import get_synthetic_model
from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.seed_locations import seed_demo_locations
from app.main import app
from app.models import Alert, Location, UserRole
from app.models.notification import NotificationOutbox
from app.models.synthetic import SyntheticAlert, SyntheticDataset, SyntheticObservation

STAMP = datetime(2025, 1, 15, 12, tzinfo=timezone.utc)
URL = "/api/synthetic/admin/alerts"


@pytest.fixture
def synthetic_setup(db, user_factory, monkeypatch):
    monkeypatch.setenv("SYNTHETIC_DEMO_ENABLED", "true")
    get_settings.cache_clear()
    seed_demo_locations(db)
    location_id = db.scalar(select(Location.id).where(Location.slug == "suva"))
    db.add(SyntheticDataset(version="synthetic-fiji-v1", metadata_json={"config": {}}, observation_count=1))
    db.flush()
    db.add(SyntheticObservation(dataset_version="synthetic-fiji-v1", location_id=location_id, observed_at=STAMP, values={}))
    db.commit()
    admin = user_factory(email="synthetic-manager@example.test", role=UserRole.MET_ADMIN)
    state = SimpleNamespace(risk="HIGH", probability=.8, status="ok")
    class Model:
        def predict(self, location_id, timestamp):
            return {"source_type": "synthetic", "location_id": location_id, "timestamp": timestamp.isoformat(),
                "status": state.status, "risk_category": state.risk, "probability": state.probability, "model_version": "synthetic-test-fixture"}
    app.dependency_overrides[get_synthetic_model] = Model
    yield state, {"location_id": location_id, "timestamp": STAMP.isoformat()}, {"Authorization": f"Bearer {create_access_token(admin.id)}"}, admin.id
    app.dependency_overrides.pop(get_synthetic_model, None)


@pytest.mark.parametrize("risk,test", [("HIGH", False), ("VERY_HIGH", False), ("LOW", True), ("MODERATE", True)])
def test_admin_creation_duplicate_identity_and_source_isolation(client, db, synthetic_setup, risk, test):
    state, payload, headers, actor = synthetic_setup
    state.risk = risk
    if test:
        assert client.post(URL, json=payload, headers=headers).status_code == 422
    created = client.post(URL, json={**payload, "test_alert": test}, headers=headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "PENDING" and body["source_type"] == "synthetic"
    assert body["is_test"] == test and body["risk_category"] == risk and body["created_by"] == actor
    assert client.post(URL, json={**payload, "test_alert": test}, headers=headers).json()["id"] == body["id"]
    assert db.scalar(select(func.count()).select_from(SyntheticAlert)) == 1
    assert db.scalar(select(func.count()).select_from(Alert)) == 0
    db.rollback()
    assert client.post(f"{URL}/{body['id']}/approve", headers=headers).status_code == 200
    assert client.get("/api/alerts/active").json() == []
    assert client.get("/api/synthetic/alerts").json()[0]["source_type"] == "synthetic"
    assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 0


@pytest.mark.parametrize("action,status", [("resolve", "RESOLVED"), ("cancel", "CANCELLED")])
def test_synthetic_closure_preserves_creator_review_and_terminal_audit(client, synthetic_setup, action, status):
    _, payload, headers, actor = synthetic_setup
    body = client.post(URL, json=payload, headers=headers).json()
    url = f"{URL}/{body['id']}"
    reviewed = client.post(url + "/approve", headers=headers).json()
    ack = client.post(url + "/acknowledge", headers=headers).json()
    assert ack["acknowledged_by"] == actor and ack["acknowledged_at"]
    assert client.post(url + "/" + action, headers=headers, json={"reason": " "}).status_code == 422
    closed = client.post(url + "/" + action, headers=headers, json={"reason": "Test completed"})
    assert closed.status_code == 200
    result = closed.json()
    assert result["status"] == status and result["closed_by"] == actor
    assert result["closed_at"] and result["closure_reason"] == "Test completed"
    assert result["created_by"] == actor and result["reviewed_at"] == reviewed["reviewed_at"]
    assert client.get("/api/synthetic/alerts").json() == []
    assert client.get(URL, headers=headers).json()[0]["status"] == status
    assert client.post(URL, json=payload, headers=headers).json()["id"] == body["id"]
    assert client.post(url + "/approve", headers=headers).status_code == 409
    assert client.post(url + "/" + action, headers=headers, json={"reason": "Overwrite"}).status_code == 409


def test_pending_cancel_stays_available_when_creation_disabled(client, synthetic_setup, monkeypatch):
    _, payload, headers, _ = synthetic_setup
    body = client.post(URL, json=payload, headers=headers).json()
    monkeypatch.setenv("SYNTHETIC_DEMO_ENABLED", "false"); get_settings.cache_clear()
    assert client.post(URL, json=payload, headers=headers).status_code == 403
    assert client.post(f"{URL}/{body['id']}/approve", headers=headers).status_code == 403
    assert client.post(f"{URL}/{body['id']}/cancel", headers=headers, json={"reason": "Cleanup"}).status_code == 200


@pytest.mark.parametrize("action", ["", "/1/approve", "/1/acknowledge", "/1/resolve", "/1/cancel"])
def test_synthetic_actions_require_admin_jwt(client, synthetic_setup, user_factory, action):
    _, payload, _, _ = synthetic_setup
    user = user_factory(email="synthetic-member@example.test")
    assert client.post(URL + action, json={**payload, "reason": "Test"}).status_code == 401
    assert client.post(URL + action, headers={"Authorization": f"Bearer {create_access_token(user.id)}"}, json=payload).status_code == 403


@pytest.mark.parametrize("status,risk,probability", [("insufficient_history", None, None), ("ongoing_simulated_flood", None, None), ("ok", "LOW", None)])
def test_test_creation_never_invents_missing_forecasts(client, synthetic_setup, status, risk, probability):
    state, payload, headers, _ = synthetic_setup
    state.status, state.risk, state.probability = status, risk, probability
    assert client.post(URL, json={**payload, "test_alert": True}, headers=headers).status_code == 422
