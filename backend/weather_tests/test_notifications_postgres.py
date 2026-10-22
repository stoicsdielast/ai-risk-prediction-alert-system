"""Safe notification workflow in a disposable PostgreSQL schema, never public data."""
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
import pytest

from weather_tests.test_postgres import postgres, pytestmark  # noqa: F401
from app.main import app
from app.core.config import get_settings
from app.core.security import create_access_token
from app.models import User, UserRole, AccountStatus, Location, Alert
from app.models.notification import SavedLocation, NotificationPreference, NotificationOutbox


def test_subscription_approval_concurrent_claim_and_durable_receipt(postgres, monkeypatch):
    engine, factory, admin_headers = postgres
    monkeypatch.setattr(get_settings(), "browser_delivery_enabled", True)
    with factory() as db:
        user = User(name="SIMULATED subscriber", email="subscriber@example.invalid", hashed_password="unused",
                    role=UserRole.COMMUNITY, status=AccountStatus.APPROVED, is_active=True)
        db.add(user)
        db.commit()
        user_id = user.id
        ids = list(db.scalars(select(Location.id).order_by(Location.id)))
    assert len(ids) == 12
    headers = {"Authorization": f"Bearer {create_access_token(user_id)}"}
    with TestClient(app) as client:
        # Concurrent PUTs must converge on one composite key, not a 500.
        def subscribe(_):
            return client.put(f"/api/me/subscriptions/{ids[0]}", headers=headers).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert list(pool.map(subscribe, range(2))) == [200, 200]
        for id in ids[1:]:
            assert client.put(f"/api/me/subscriptions/{id}", headers=headers).status_code == 200
        assert len(client.get("/api/me/subscriptions", headers=headers).json()) == 12
        assert client.put("/api/me/notification-preferences", headers=headers, json={"browser_enabled": True}).status_code == 200
        draft = client.post("/api/admin/alerts", headers=admin_headers, json={
            "location_id": ids[0], "severity": "HIGH", "message": "SIMULATED TEST ONLY — not a real warning"}).json()
        alert_id = draft["id"]
        def approve(_):
            return client.patch(f"/api/admin/alerts/{alert_id}/approve", headers=admin_headers).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(approve, range(2))) == [200, 409]
        rows = client.get("/api/me/notifications", headers=headers).json()
        assert len(rows) == 1
        notification_id = rows[0]["id"]
        def claim(_):
            return client.post(f"/api/me/notifications/{notification_id}/claim", headers=headers)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, range(2)))
        assert sorted(r.status_code for r in results) == [200, 409]
        claimed = next(r.json() for r in results if r.status_code == 200)
        receipt = {"token": claimed["token"], "outcome": "DELIVERED"}
        for _ in range(2):
            assert client.post(f"/api/me/notifications/{notification_id}/receipt", headers=headers, json=receipt).status_code == 200
    with factory() as db:
        row = db.get(NotificationOutbox, notification_id)
        assert row.status == "DELIVERED" and row.delivered_at is not None and row.attempts == 1
        assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 1
        db.add(NotificationOutbox(user_id=user_id, alert_id=alert_id))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.scalar(select(func.count()).select_from(SavedLocation)) == 12


def test_notification_migration_preserves_operational_data(postgres):
    from alembic import command
    from alembic.config import Config
    _, factory, _ = postgres
    with factory() as db:
        before = list(db.scalars(select(Location.name).order_by(Location.id)))
        users = db.scalar(select(func.count()).select_from(User))
    # Only this fixture's empty new tables are dropped; the real database is untouched.
    command.downgrade(Config("alembic.ini"), "20261022_alert_expiry")
    command.upgrade(Config("alembic.ini"), "head")
    with factory() as db:
        assert list(db.scalars(select(Location.name).order_by(Location.id))) == before
        assert db.scalar(select(func.count()).select_from(User)) == users
        assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 0
