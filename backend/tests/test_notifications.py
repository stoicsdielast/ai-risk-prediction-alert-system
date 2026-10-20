"""Explicitly simulated fixtures in isolated databases; no real warning delivery."""
from datetime import timedelta

import pytest
from sqlalchemy import select, func
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from app.core.security import create_access_token
from app.models import Alert, Location, Division, UserRole, AccountStatus
from app.models.notification import NotificationOutbox, SavedLocation, NotificationAttempt
from app.services import notification_outbox as outbox


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
def setup(client, session_factory, user_factory, monkeypatch):
    monkeypatch.setattr(get_settings(), "browser_delivery_enabled", True)
    admin = user_factory(email="notify-admin@example.invalid", role=UserRole.MET_ADMIN)
    user = user_factory(email="notify-user@example.invalid")
    other = user_factory(email="notify-other@example.invalid")
    with session_factory() as db:
        locations = [Location(slug=f"test-{i}", name=f"SIMULATED location {i}",
                    division=Division.CENTRAL, latitude=-18, longitude=178) for i in range(2)]
        db.add_all(locations)
        db.commit()
    return admin, user, other, locations


def opt_in(client, user, location):
    assert client.put(f"/api/me/subscriptions/{location.id}", headers=auth(user)).status_code == 200
    assert client.put("/api/me/notification-preferences", headers=auth(user), json={"browser_enabled": True}).status_code == 200


def approve(client, admin, location):
    draft = client.post("/api/admin/alerts", headers=auth(admin), json={
        "location_id": location.id, "severity": "HIGH", "message": "SIMULATED TEST ONLY — not a real emergency warning"})
    assert draft.status_code == 201, draft.text
    result = client.patch(f"/api/admin/alerts/{draft.json()['id']}/approve", headers=auth(admin))
    assert result.status_code == 200, result.text
    return result.json()["id"]


def history(client, user):
    result = client.get("/api/me/notifications", headers=auth(user))
    assert result.status_code == 200, result.text
    return result.json()


def test_subscriptions_multiple_idempotent_private(client, setup, session_factory):
    _, user, other, locations = setup
    for loc in locations:
        opt_in(client, user, loc)
        opt_in(client, user, loc)
    assert len(client.get("/api/me/subscriptions", headers=auth(user)).json()) == 2
    assert client.get("/api/me/subscriptions", headers=auth(other)).json() == []
    assert client.delete(f"/api/me/subscriptions/{locations[0].id}", headers=auth(other)).status_code == 204
    assert len(client.get("/api/me/subscriptions", headers=auth(user)).json()) == 2
    assert client.delete(f"/api/me/subscriptions/{locations[0].id}", headers=auth(user)).status_code == 204
    assert len(client.get("/api/me/subscriptions", headers=auth(user)).json()) == 1
    assert client.put("/api/me/subscriptions/99999", headers=auth(user)).status_code == 404
    with session_factory() as db:
        db.get(Location, locations[1].id).is_active = False
        db.commit()
    assert client.put(f"/api/me/subscriptions/{locations[1].id}", headers=auth(user)).status_code == 409


@pytest.mark.parametrize("path", ["subscriptions", "notification-preferences", "notifications"])
def test_requires_auth(client, path):
    assert client.get(f"/api/me/{path}").status_code == 401


@pytest.mark.parametrize("state", [AccountStatus.PENDING, AccountStatus.REJECTED])
def test_ineligible_accounts_denied(client, user_factory, state):
    user = user_factory(email="blocked@example.invalid", account_status=state)
    assert client.get("/api/me/notifications", headers=auth(user)).status_code == 403


def test_approval_targets_only_subscribed_opted_users_and_claim_is_exclusive(client, setup, session_factory):
    admin, user, other, locations = setup
    opt_in(client, user, locations[0])
    client.put(f"/api/me/subscriptions/{locations[0].id}", headers=auth(other))
    alert_id = approve(client, admin, locations[0])
    approve(client, admin, locations[1])
    assert history(client, other) == []
    rows = history(client, user)
    assert len(rows) == 1
    id = rows[0]["id"]
    assert client.post(f"/api/me/notifications/{id}/claim", headers=auth(other)).status_code == 404
    claimed = client.post(f"/api/me/notifications/{id}/claim", headers=auth(user)).json()
    assert claimed["alert"]["id"] == alert_id
    assert client.post(f"/api/me/notifications/{id}/claim", headers=auth(user)).status_code == 409
    receipt = {"token": claimed["token"], "outcome": "DELIVERED"}
    for _ in range(2):
        assert client.post(f"/api/me/notifications/{id}/receipt", headers=auth(user), json=receipt).status_code == 200
    assert history(client, user)[0]["delivered_at"]
    assert client.post(f"/api/me/notifications/{id}/claim", headers=auth(user)).status_code == 409
    with session_factory() as db:
        outbox.enqueue(db, db.get(Alert, alert_id))
        db.commit()
        assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 1


def test_failed_delivery_retries_without_new_record_and_preserves_attempts(client, setup, session_factory):
    admin, user, _, locations = setup
    opt_in(client, user, locations[0])
    approve(client, admin, locations[0])
    id = history(client, user)[0]["id"]
    claim = client.post(f"/api/me/notifications/{id}/claim", headers=auth(user)).json()
    failure = {"token": claim["token"], "outcome": "FAILED", "error": "Simulated browser failure"}
    assert client.post(f"/api/me/notifications/{id}/receipt", headers=auth(user), json=failure).status_code == 200
    assert client.post(f"/api/me/notifications/{id}/claim", headers=auth(user)).status_code == 409
    with session_factory() as db:
        db.get(NotificationOutbox, id).next_attempt_at = outbox.now() - timedelta(seconds=1)
        db.commit()
    second = client.post(f"/api/me/notifications/{id}/claim", headers=auth(user)).json()
    assert second["token"] != claim["token"]
    assert client.post(f"/api/me/notifications/{id}/receipt", headers=auth(user), json=failure).status_code == 409
    assert client.post(f"/api/me/notifications/{id}/receipt", headers=auth(user), json={
        "token": second["token"], "outcome": "DELIVERED"}).status_code == 200
    attempts = client.get(f"/api/me/notifications/{id}/attempts", headers=auth(user)).json()
    assert [a["outcome"] for a in attempts] == ["FAILED", "DELIVERED"]
    assert attempts[0]["error"] == "Simulated browser failure"


@pytest.mark.parametrize("change", ["suppress", "expire", "unsubscribe", "disable", "inactive"])
def test_delivery_rechecks_eligibility(client, setup, session_factory, change):
    admin, user, _, locations = setup
    opt_in(client, user, locations[0])
    alert_id = approve(client, admin, locations[0])
    id = history(client, user)[0]["id"]
    if change == "suppress":
        client.patch(f"/api/admin/alerts/{alert_id}/suppress", headers=auth(admin), json={"reason": "SIMULATED withdrawal"})
    elif change == "unsubscribe":
        client.delete(f"/api/me/subscriptions/{locations[0].id}", headers=auth(user))
    elif change == "disable":
        client.put("/api/me/notification-preferences", headers=auth(user), json={"browser_enabled": False})
    else:
        with session_factory() as db:
            if change == "expire":
                db.get(Alert, alert_id).expires_at = outbox.now() - timedelta(seconds=1)
            else:
                db.get(Location, locations[0].id).is_active = False
            db.commit()
    assert client.post(f"/api/me/notifications/{id}/claim", headers=auth(user)).status_code == 409
    assert history(client, user)[0]["status"] == "CANCELLED"


def test_outbox_failure_rolls_back_approval(client, setup, monkeypatch, session_factory):
    admin, user, _, locations = setup
    opt_in(client, user, locations[0])
    draft = client.post("/api/admin/alerts", headers=auth(admin), json={
        "location_id": locations[0].id, "severity": "HIGH", "message": "SIMULATED rollback"}).json()
    def fail(db, alert):
        raise OperationalError("test", {}, Exception("private"))
    monkeypatch.setattr(outbox, "enqueue", fail)
    assert client.patch(f"/api/admin/alerts/{draft['id']}/approve", headers=auth(admin)).status_code == 500
    with session_factory() as db:
        assert db.get(Alert, draft["id"]).status.value == "PENDING"
        assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 0


def test_operator_gate_and_preference_validation(client, setup, monkeypatch):
    admin, user, _, locations = setup
    assert client.put("/api/me/notification-preferences", headers=auth(user), json={"browser_enabled": True, "user_id": 1}).status_code == 422
    opt_in(client, user, locations[0])
    approve(client, admin, locations[0])
    monkeypatch.setattr(get_settings(), "browser_delivery_enabled", False)
    id = history(client, user)[0]["id"]
    assert client.post(f"/api/me/notifications/{id}/claim", headers=auth(user)).status_code == 409


def test_suppression_after_claim_blocks_pre_display_check_and_receipt(client, setup):
    admin, user, _, locations = setup
    opt_in(client, user, locations[0])
    alert_id = approve(client, admin, locations[0])
    id = history(client, user)[0]["id"]
    claim = client.post(f"/api/me/notifications/{id}/claim", headers=auth(user)).json()
    client.patch(f"/api/admin/alerts/{alert_id}/suppress", headers=auth(admin), json={"reason": "SIMULATED withdrawal"})
    assert client.post(f"/api/me/notifications/{id}/check", headers=auth(user), json={"token": claim["token"]}).status_code == 409
    result = client.post(f"/api/me/notifications/{id}/receipt", headers=auth(user), json={"token": claim["token"], "outcome": "DELIVERED"})
    assert result.json()["status"] == "CANCELLED" and result.json()["delivered_at"] is None


def test_abandoned_claim_recovers_and_retry_limit_is_bounded(client, setup, session_factory):
    admin, user, _, locations = setup
    opt_in(client, user, locations[0])
    approve(client, admin, locations[0])
    id = history(client, user)[0]["id"]
    for _ in range(outbox.MAX_ATTEMPTS):
        assert client.post(f"/api/me/notifications/{id}/claim", headers=auth(user)).status_code == 200
        with session_factory() as db:
            db.get(NotificationOutbox, id).claimed_until = outbox.now() - timedelta(seconds=1)
            db.commit()
    assert client.post(f"/api/me/notifications/{id}/claim", headers=auth(user)).status_code == 409
    assert history(client, user)[0]["status"] == "FAILED"
    attempts = client.get(f"/api/me/notifications/{id}/attempts", headers=auth(user)).json()
    assert len(attempts) == 5 and all(a["outcome"] == "FAILED" for a in attempts)


def test_synthetic_object_cannot_enqueue_even_with_colliding_id(setup, session_factory):
    from app.models import SyntheticAlert
    with session_factory() as db:
        outbox.enqueue(db, SyntheticAlert(id=1, prediction_id=1, status="APPROVED", created_by=1))
        assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 0
