"""Closure never deletes history, republishes a warning, or resets event cooldowns."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.seed_locations import seed_demo_locations
from app.models import Alert, Location, Prediction, RiskLevel, UserRole


@pytest.fixture
def managed(db, user_factory):
    seed_demo_locations(db)
    location_id = db.scalar(select(Location.id).where(Location.slug == "suva"))
    db.rollback()
    admin = user_factory(email="lifecycle-admin@example.test", role=UserRole.MET_ADMIN)
    return location_id, admin.id, {"Authorization": f"Bearer {create_access_token(admin.id)}"}


def draft(client, managed):
    location_id, _, headers = managed
    response = client.post("/api/admin/alerts", headers=headers, json={
        "location_id": location_id, "severity": "HIGH", "message": "TEST ONLY: lifecycle fixture"})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("action,status", [("resolve", "RESOLVED"), ("cancel", "CANCELLED")])
def test_terminal_actions_retain_approval_actor_reason_and_history(client, managed, action, status):
    alert = draft(client, managed)
    _, actor, headers = managed
    url = f"/api/admin/alerts/{alert['id']}"
    approved = client.patch(url + "/approve", headers=headers).json()
    assert client.get("/api/alerts/active").json()
    assert client.patch(url + "/" + action, headers=headers, json={"reason": "  "}).status_code == 422
    closed = client.patch(url + "/" + action, headers=headers, json={"reason": "Test exercise completed"})
    assert closed.status_code == 200, closed.text
    body = closed.json()
    assert body["status"] == status and body["closed_by_user_id"] == actor
    assert body["closed_at"].endswith("Z") and body["closure_reason"] == "Test exercise completed"
    assert body["approved_by_user_id"] == actor and body["approved_at"] == approved["approved_at"]
    assert body["expires_at"] == approved["expires_at"]
    assert client.get("/api/alerts/active").json() == []
    assert client.get(url, headers=headers).json() == body
    assert client.get(f"/api/admin/alerts?status={status}", headers=headers).json()[0]["id"] == alert["id"]
    assert client.patch(url + "/approve", headers=headers).status_code == 409
    assert client.patch(url + "/" + action, headers=headers, json={"reason": "Overwrite attempt"}).status_code == 409
    assert client.delete(url, headers=headers).status_code == 405


def test_acknowledgement_is_idempotent_and_does_not_withdraw_warning(client, managed):
    alert = draft(client, managed)
    _, actor, headers = managed
    url = f"/api/admin/alerts/{alert['id']}"
    assert client.patch(url + "/acknowledge", headers=headers).status_code == 409
    assert client.patch(url + "/resolve", headers=headers, json={"reason": "Pending"}).status_code == 409
    client.patch(url + "/approve", headers=headers)
    first = client.patch(url + "/acknowledge", headers=headers).json()
    again = client.patch(url + "/acknowledge", headers=headers).json()
    assert first["acknowledged_by_user_id"] == actor
    assert first["acknowledged_at"] == again["acknowledged_at"]
    assert client.get("/api/alerts/active").json()[0]["id"] == alert["id"]
    assert "acknowledged_by_user_id" not in client.get("/api/alerts/active").json()[0]


def test_pending_alert_can_be_cancelled_with_audit(client, managed):
    alert = draft(client, managed)
    result = client.patch(f"/api/admin/alerts/{alert['id']}/cancel", headers=managed[2], json={"reason": "Incorrect location"})
    assert result.status_code == 200
    assert result.json()["approved_at"] is None and result.json()["closure_reason"] == "Incorrect location"


@pytest.mark.parametrize("action", ["acknowledge", "resolve", "cancel"])
def test_management_requires_current_approved_admin(client, managed, user_factory, action):
    alert = draft(client, managed)
    community = user_factory(email=f"member-{action}@example.test")
    url = f"/api/admin/alerts/{alert['id']}/{action}"
    assert client.patch(url, json={"reason": "Test"}).status_code == 401
    assert client.patch(url, headers={"Authorization": "Bearer invalid"}, json={"reason": "Test"}).status_code == 401
    assert client.patch(url, headers={"Authorization": f"Bearer {create_access_token(community.id)}"}, json={"reason": "Test"}).status_code == 403


def test_expired_records_remain_readable_and_cannot_be_acknowledged(client, managed, db):
    alert = draft(client, managed)
    url = f"/api/admin/alerts/{alert['id']}"
    client.patch(url + "/approve", headers=managed[2])
    db.get(Alert, alert["id"]).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert client.get("/api/alerts/active").json() == []
    assert client.get(url, headers=managed[2]).json()["status"] == "APPROVED"
    assert client.patch(url + "/acknowledge", headers=managed[2]).status_code == 409


@pytest.mark.parametrize("action", ["resolve", "cancel"])
def test_closing_does_not_bypass_prediction_cooldown(client, managed, db, action):
    alert = draft(client, managed)
    url = f"/api/admin/alerts/{alert['id']}"
    client.patch(url + "/approve", headers=managed[2])
    client.patch(url + "/" + action, headers=managed[2], json={"reason": "Test closure"})
    prediction = Prediction(location_id=managed[0], risk_level=RiskLevel.HIGH, flood_probability=.7,
        model_version="test-only-lifecycle", predicted_at=datetime.now(timezone.utc), is_sample=False)
    db.add(prediction); db.commit()
    result = client.post(f"/api/admin/alerts/from-prediction/{prediction.id}", headers=managed[2])
    assert result.status_code == 200 and result.json()["id"] == alert["id"]
    assert result.json()["status"] in ("RESOLVED", "CANCELLED")


@pytest.mark.parametrize("risk", [RiskLevel.LOW, RiskLevel.MODERATE])
def test_low_risk_operational_predictions_do_not_create_alerts(client, managed, db, risk):
    prediction = Prediction(location_id=managed[0], risk_level=risk, flood_probability=.1,
        model_version="test-only-low-risk", predicted_at=datetime.now(timezone.utc), is_sample=False)
    db.add(prediction); db.commit()
    response = client.post(f"/api/admin/alerts/from-prediction/{prediction.id}", headers=managed[2])
    assert response.status_code == 200 and response.json() is None
