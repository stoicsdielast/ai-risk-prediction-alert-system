"""Alert lifecycle tests use explicitly labelled fixtures, never operational predictions."""

from datetime import datetime, timedelta, timezone
from itertools import count

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import (
    AccountStatus, Alert, AlertSource, AlertStatus, Division, Location, Prediction, RiskLevel,
    UserRole,
)
from app.services import alert_service, notification_service

ADMIN_URL = "/api/admin/alerts"
PUBLIC_URL = "/api/alerts/active"


def authorization(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
def admin(user_factory):
    return user_factory(email="alert-admin@example.com", role=UserRole.MET_ADMIN)


@pytest.fixture
def location_factory(session_factory):
    slugs = (f"test-location-{number}" for number in count(1))

    def create(*, active=True, name="TEST ONLY — monitored location"):
        with session_factory() as db:
            location = Location(
                slug=next(slugs), name=name, division=Division.CENTRAL,
                latitude=-18.14, longitude=178.44, is_active=active,
            )
            db.add(location)
            db.commit()
            return location
    return create


@pytest.fixture
def location(location_factory):
    return location_factory()


@pytest.fixture
def prediction_factory(session_factory, location):
    def create(risk=RiskLevel.HIGH, *, location_id=None, is_sample=False):
        # Controlled fixtures exercise threshold branches; no ML results are invented.
        probability = {
            RiskLevel.LOW: 0.1, RiskLevel.MODERATE: 0.3,
            RiskLevel.HIGH: 0.7, RiskLevel.VERY_HIGH: 0.9,
        }[risk]
        with session_factory() as db:
            prediction = Prediction(
                location_id=location_id or location.id, risk_level=risk,
                flood_probability=probability, model_version="test-fixture-not-an-ml-result",
                predicted_at=datetime.now(timezone.utc),
                is_sample=is_sample,
            )
            db.add(prediction)
            db.commit()
            return prediction
    return create


def manual_alert(client, admin, location_id, **extra):
    response = client.post(ADMIN_URL, headers=authorization(admin), json={
        "location_id": location_id, "severity": "HIGH",
        "message": "Test-only draft alert; not an operational Fiji MET warning.", **extra,
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_location_picker_id_supports_persisted_manual_alert_workflow(client, admin, location):
    locations = client.get("/api/locations").json()
    selected = next(item for item in locations if item["name"] == location.name)
    assert selected["id"] == location.id
    alert = manual_alert(client, admin, selected["id"])
    url = f"{ADMIN_URL}/{alert['id']}"
    changed = client.patch(url, headers=authorization(admin), json={
        "message": "Test-only community warning", "severity": "VERY_HIGH",
    })
    assert changed.status_code == 200
    assert client.get(url, headers=authorization(admin)).json()["message"] == "Test-only community warning"
    assert client.patch(url + "/approve", headers=authorization(admin)).status_code == 200
    public = client.get(PUBLIC_URL).json()
    assert len(public) == 1
    assert public[0]["location"]["id"] == selected["id"]
    assert public[0]["severity"] == "VERY_HIGH"
    assert public[0]["created_at"] and public[0]["approved_at"]
    assert client.patch(url + "/suppress", headers=authorization(admin), json={
        "reason": "Test-only withdrawal",
    }).status_code == 200
    assert client.get(PUBLIC_URL).json() == []


@pytest.mark.parametrize("risk", [RiskLevel.HIGH, RiskLevel.VERY_HIGH])
def test_high_risk_prediction_creates_only_pending_recommendation(
    client, admin, prediction_factory, risk, monkeypatch,
):
    prediction = prediction_factory(risk)
    calls = []
    monkeypatch.setattr(notification_service, "notify_users_for_approved_alert", lambda alert: calls.append(alert.id))
    response = client.post(f"{ADMIN_URL}/from-prediction/{prediction.id}", headers=authorization(admin))
    assert response.status_code == 200
    alert = response.json()
    assert alert["status"] == "PENDING"
    assert alert["source"] == "AI_RECOMMENDATION"
    assert alert["severity"] == risk.value
    assert alert["prediction_id"] == prediction.id
    assert alert["location_id"] == prediction.location_id
    assert alert["approved_at"] is None
    assert alert["approved_by_user_id"] is None
    assert "AI-generated" in alert["message"]
    assert alert["prediction"]["confidence_percent"] == pytest.approx(prediction.flood_probability * 100)
    assert calls == []
    assert client.get(PUBLIC_URL).json() == []


@pytest.mark.parametrize("risk", [RiskLevel.LOW, RiskLevel.MODERATE])
def test_lower_risk_prediction_does_not_create_alert(client, admin, prediction_factory, session_factory, risk):
    prediction = prediction_factory(risk)
    response = client.post(f"{ADMIN_URL}/from-prediction/{prediction.id}", headers=authorization(admin))
    assert response.status_code == 200
    assert response.json() is None
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Alert)) == 0


@pytest.mark.parametrize("risk", list(RiskLevel))
def test_sample_prediction_cannot_create_recommendation(
    client, admin, prediction_factory, session_factory, risk,
):
    prediction = prediction_factory(risk, is_sample=True)
    response = client.post(f"{ADMIN_URL}/from-prediction/{prediction.id}", headers=authorization(admin))
    assert response.status_code == 400
    assert response.json() == {"detail": "Sample predictions cannot be used for alerts"}
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Alert)) == 0
        assert db.get(Prediction, prediction.id).is_sample is True


def test_sample_flag_is_read_from_storage(session_factory, prediction_factory):
    prediction = prediction_factory(is_sample=True)
    prediction.is_sample = False
    with session_factory() as db:
        with pytest.raises(alert_service.InvalidAlertDataError, match="Sample predictions"):
            alert_service.create_alert_from_prediction(db, prediction)
        assert db.scalar(select(func.count()).select_from(Alert)) == 0


def test_sample_prediction_cannot_be_attached_to_manual_alert(
    client, admin, prediction_factory, session_factory,
):
    prediction = prediction_factory(is_sample=True)
    response = client.post(ADMIN_URL, headers=authorization(admin), json={
        "location_id": prediction.location_id, "prediction_id": prediction.id,
        "severity": "HIGH", "message": "Test-only sample must not become a warning",
    })
    assert response.status_code == 400
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Alert)) == 0


@pytest.mark.parametrize("source", list(AlertSource))
def test_old_sample_alert_cannot_be_approved_or_published(
    client, admin, prediction_factory, session_factory, monkeypatch, source,
):
    prediction = prediction_factory(is_sample=True)
    calls = []
    monkeypatch.setattr(notification_service, "notify_users_for_approved_alert", lambda alert: calls.append(alert.id))
    with session_factory() as db:
        alert = Alert(
            location_id=prediction.location_id, prediction_id=prediction.id,
            severity=RiskLevel.HIGH, source=source, status=AlertStatus.PENDING,
            message="Test-only legacy sample alert", created_by_user_id=admin.id,
        )
        db.add(alert)
        db.commit()
        alert_id = alert.id
    response = client.patch(f"{ADMIN_URL}/{alert_id}/approve", headers=authorization(admin))
    assert response.status_code == 400
    assert calls == []
    with session_factory() as db:
        alert = db.get(Alert, alert_id)
        assert alert.status == AlertStatus.PENDING
        assert alert.approved_at is None
        # Simulate an alert approved before the sample guard was installed.
        alert.status = AlertStatus.APPROVED
        alert.approved_by_user_id = admin.id
        alert.approved_at = datetime.now(timezone.utc)
        db.commit()
    assert client.get(PUBLIC_URL).json() == []


def test_repeated_ai_request_reuses_existing_alert(client, admin, prediction_factory, session_factory):
    prediction = prediction_factory()
    url = f"{ADMIN_URL}/from-prediction/{prediction.id}"
    first = client.post(url, headers=authorization(admin)).json()
    second = client.post(url, headers=authorization(admin)).json()
    assert first["id"] == second["id"]
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Alert)) == 1


@pytest.mark.parametrize("action", ["approve", "reject", "suppress"])
def test_retry_never_revives_a_reviewed_ai_alert(client, admin, prediction_factory, action):
    prediction = prediction_factory()
    url = f"{ADMIN_URL}/from-prediction/{prediction.id}"
    alert = client.post(url, headers=authorization(admin)).json()
    arguments = {"json": {"reason": "Test-only withdrawal"}} if action == "suppress" else {}
    reviewed = client.patch(f"{ADMIN_URL}/{alert['id']}/{action}", headers=authorization(admin), **arguments)
    assert reviewed.status_code == 200
    retried = client.post(url, headers=authorization(admin))
    assert retried.status_code == 200
    assert retried.json()["id"] == alert["id"]
    assert retried.json()["status"] == reviewed.json()["status"]


def test_prediction_and_alert_roll_back_together(session_factory, location):
    with session_factory() as db:
        prediction = Prediction(
            location_id=location.id, risk_level=RiskLevel.HIGH,
            flood_probability=0.7, model_version="test-fixture-not-an-ml-result",
        )
        db.add(prediction)
        db.flush()
        alert = alert_service.create_alert_from_prediction(db, prediction)
        assert alert.id is not None
        db.rollback()
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Prediction)) == 0
        assert db.scalar(select(func.count()).select_from(Alert)) == 0


def test_helper_does_not_commit_alert_for_previously_saved_prediction(session_factory, prediction_factory):
    prediction = prediction_factory()
    with session_factory() as db:
        alert_service.create_alert_from_prediction(db, prediction)
        db.rollback()
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Alert)) == 0
        assert db.get(Prediction, prediction.id) is not None


def test_unique_constraint_prevents_duplicate_when_service_is_bypassed(
    client, admin, prediction_factory, session_factory,
):
    prediction = prediction_factory()
    client.post(f"{ADMIN_URL}/from-prediction/{prediction.id}", headers=authorization(admin))
    with session_factory() as db:
        db.add(Alert(
            location_id=prediction.location_id, prediction_id=prediction.id,
            severity=RiskLevel.HIGH, source=AlertSource.AI_RECOMMENDATION,
            message="Test-only duplicate attempt", status=AlertStatus.PENDING,
        ))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_manual_admin_alert_is_pending_and_audited(client, admin, location):
    alert = manual_alert(client, admin, location.id)
    assert alert["source"] == "MET_OFFICIAL"
    assert alert["status"] == "PENDING"
    assert alert["created_by_user_id"] == admin.id
    assert alert["prediction"] is None
    assert alert["location"]["name"] == location.name
    assert alert["location"]["is_active"] is True
    assert alert["created_at"].endswith("Z")
    assert client.get(PUBLIC_URL).json() == []


def test_manual_alert_can_reference_prediction_and_automatic_retry_reuses_it(client, admin, prediction_factory):
    prediction = prediction_factory()
    alert = manual_alert(client, admin, prediction.location_id, prediction_id=prediction.id)
    automatic = client.post(f"{ADMIN_URL}/from-prediction/{prediction.id}", headers=authorization(admin))
    assert automatic.json()["id"] == alert["id"]
    assert automatic.json()["source"] == "MET_OFFICIAL"
    duplicate = client.post(ADMIN_URL, headers=authorization(admin), json={
        "location_id": prediction.location_id, "prediction_id": prediction.id,
        "severity": "HIGH", "message": "Test-only duplicate draft",
    })
    assert duplicate.status_code == 409


@pytest.mark.parametrize(("method", "path", "body"), [
    ("GET", ADMIN_URL, None), ("GET", ADMIN_URL + "/1", None),
    ("POST", ADMIN_URL, {"location_id": 1, "severity": "HIGH", "message": "Test-only draft"}),
    ("POST", ADMIN_URL + "/from-prediction/1", None),
    ("PATCH", ADMIN_URL + "/1", {"message": "Test-only edit"}),
    ("PATCH", ADMIN_URL + "/1/approve", None), ("PATCH", ADMIN_URL + "/1/reject", None),
    ("PATCH", ADMIN_URL + "/1/suppress", {"reason": "Test-only withdrawal"}),
])
@pytest.mark.parametrize("identity", ["anonymous", "community"])
def test_all_admin_alert_actions_require_existing_jwt_admin_role(client, user_factory, method, path, body, identity):
    headers = {}
    if identity == "community":
        headers = authorization(user_factory(email="alert-community@example.com"))
    response = client.request(method, path, headers=headers, **({"json": body} if body else {}))
    assert response.status_code == (401 if identity == "anonymous" else 403)


@pytest.mark.parametrize(("account_status", "active"), [
    (AccountStatus.PENDING, True), (AccountStatus.REJECTED, True), (AccountStatus.APPROVED, False),
])
def test_unapproved_or_inactive_met_admin_cannot_access_alerts(client, user_factory, account_status, active):
    admin = user_factory(
        email="ineligible-alert-admin@example.com", role=UserRole.MET_ADMIN,
        account_status=account_status, is_active=active,
    )
    assert client.get(ADMIN_URL, headers=authorization(admin)).status_code == 403


def test_admin_approval_persists_audit_and_exposes_safe_public_response(
    client, admin, location, session_factory, monkeypatch,
):
    alert = manual_alert(client, admin, location.id)
    calls = []

    def hook(approved):
        # A separate database session can see approval before the hook runs.
        with session_factory() as db:
            stored = db.get(Alert, approved.id)
            assert stored.status == AlertStatus.APPROVED
            assert stored.approved_by_user_id == admin.id
        calls.append(approved.id)

    monkeypatch.setattr(notification_service, "notify_users_for_approved_alert", hook)
    response = client.patch(f"{ADMIN_URL}/{alert['id']}/approve", headers=authorization(admin))
    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"
    assert response.json()["approved_by_user_id"] == admin.id
    assert response.json()["approved_at"].endswith("Z")
    assert calls == [alert["id"]]
    public = client.get(PUBLIC_URL)
    assert public.status_code == 200
    assert len(public.json()) == 1
    assert public.json()[0]["id"] == alert["id"]
    assert set(public.json()[0]) == {
        "id", "is_demo", "location_id", "location", "prediction_id", "prediction", "severity",
        "status", "source", "message", "created_at", "approved_at", "expires_at",
    }
    assert set(public.json()[0]["location"]) == {"id", "name"}
    assert "hashed_password" not in public.text
    assert "approved_by_user_id" not in public.text
    assert "suppression_reason" not in public.text
    repeated = client.patch(f"{ADMIN_URL}/{alert['id']}/approve", headers=authorization(admin))
    assert repeated.status_code == 409
    assert calls == [alert["id"]]


def test_public_ai_alert_includes_real_record_reference_after_review(client, admin, prediction_factory):
    prediction = prediction_factory()
    alert = client.post(f"{ADMIN_URL}/from-prediction/{prediction.id}", headers=authorization(admin)).json()
    client.patch(f"{ADMIN_URL}/{alert['id']}/approve", headers=authorization(admin))
    public = client.get(PUBLIC_URL).json()[0]
    assert public["source"] == "AI_RECOMMENDATION"
    assert public["prediction"]["id"] == prediction.id
    assert public["prediction"]["model_version"] == prediction.model_version
    assert public["prediction"]["risk_level"] == "HIGH"


def test_edit_pending_message_and_severity_records_editor_without_publishing(client, admin, location):
    alert = manual_alert(client, admin, location.id)
    response = client.patch(f"{ADMIN_URL}/{alert['id']}", headers=authorization(admin), json={
        "message": "  Updated test-only review message  ", "severity": "VERY_HIGH",
    })
    assert response.status_code == 200
    assert response.json()["message"] == "Updated test-only review message"
    assert response.json()["severity"] == "VERY_HIGH"
    assert response.json()["updated_by_user_id"] == admin.id
    assert response.json()["updated_at"].endswith("Z")
    assert response.json()["status"] == "PENDING"
    assert client.get(PUBLIC_URL).json() == []


@pytest.mark.parametrize("action", ["approve", "reject", "suppress"])
def test_reviewed_alert_cannot_be_edited(client, admin, location, action):
    alert = manual_alert(client, admin, location.id)
    body = {"reason": "Test-only withdrawal"} if action == "suppress" else None
    reviewed = client.patch(
        f"{ADMIN_URL}/{alert['id']}/{action}", headers=authorization(admin),
        **({"json": body} if body else {}),
    )
    assert reviewed.status_code == 200
    edit = client.patch(f"{ADMIN_URL}/{alert['id']}", headers=authorization(admin), json={"severity": "LOW"})
    assert edit.status_code == 409


@pytest.mark.parametrize("action", ["reject", "suppress"])
def test_unpublished_terminal_alerts_remain_private_and_audited(client, admin, location, session_factory, action):
    alert = manual_alert(client, admin, location.id)
    reason = "Incorrect test-only recommendation"
    arguments = {"json": {"reason": reason}} if action == "suppress" else {}
    reviewed = client.patch(f"{ADMIN_URL}/{alert['id']}/{action}", headers=authorization(admin), **arguments)
    assert reviewed.status_code == 200
    terminal = reviewed.json()
    prefix = "rejected" if action == "reject" else "suppressed"
    assert terminal[f"{prefix}_by_user_id"] == admin.id
    assert terminal[f"{prefix}_at"].endswith("Z")
    if action == "suppress":
        assert terminal["suppression_reason"] == reason
    assert client.get(PUBLIC_URL).json() == []
    assert client.get(f"{ADMIN_URL}/{alert['id']}", headers=authorization(admin)).status_code == 200
    assert client.patch(f"{ADMIN_URL}/{alert['id']}/approve", headers=authorization(admin)).status_code == 409
    with session_factory() as db:
        assert db.get(Alert, alert["id"]) is not None


def test_suppressing_approved_alert_removes_public_visibility_and_keeps_approval_audit(client, admin, location):
    alert = manual_alert(client, admin, location.id)
    approved = client.patch(f"{ADMIN_URL}/{alert['id']}/approve", headers=authorization(admin)).json()
    suppressed = client.patch(f"{ADMIN_URL}/{alert['id']}/suppress", headers=authorization(admin), json={
        "reason": "  Test-only conditions changed  ",
    })
    assert suppressed.status_code == 200
    assert suppressed.json()["status"] == "SUPPRESSED"
    assert suppressed.json()["suppression_reason"] == "Test-only conditions changed"
    assert suppressed.json()["approved_at"] == approved["approved_at"]
    assert suppressed.json()["approved_by_user_id"] == admin.id
    assert client.get(PUBLIC_URL).json() == []
    assert client.patch(f"{ADMIN_URL}/{alert['id']}/suppress", headers=authorization(admin), json={
        "reason": "Test-only repeated action",
    }).status_code == 409


def test_approved_alert_cannot_be_rejected(client, admin, location):
    alert = manual_alert(client, admin, location.id)
    client.patch(f"{ADMIN_URL}/{alert['id']}/approve", headers=authorization(admin))
    assert client.patch(f"{ADMIN_URL}/{alert['id']}/reject", headers=authorization(admin)).status_code == 409


@pytest.mark.parametrize("body", [{}, {"reason": ""}, {"reason": "   "}, {"reason": None}])
def test_suppression_requires_a_nonblank_reason(client, admin, location, body):
    alert = manual_alert(client, admin, location.id)
    response = client.patch(f"{ADMIN_URL}/{alert['id']}/suppress", headers=authorization(admin), json=body)
    assert response.status_code == 422
    assert client.get(f"{ADMIN_URL}/{alert['id']}", headers=authorization(admin)).json()["status"] == "PENDING"


def test_invalid_or_inactive_location_is_rejected(client, admin, location_factory):
    inactive = location_factory(active=False)
    for location_id, expected in [(999999, 404), (inactive.id, 400)]:
        response = client.post(ADMIN_URL, headers=authorization(admin), json={
            "location_id": location_id, "severity": "HIGH", "message": "Test-only draft",
        })
        assert response.status_code == expected


def test_deactivating_location_blocks_approval_and_hides_previously_approved_alert(
    client, admin, location, session_factory,
):
    pending = manual_alert(client, admin, location.id)
    approved = manual_alert(client, admin, location.id)
    client.patch(f"{ADMIN_URL}/{approved['id']}/approve", headers=authorization(admin))
    with session_factory() as db:
        db.get(Location, location.id).is_active = False
        db.commit()
    response = client.patch(f"{ADMIN_URL}/{pending['id']}/approve", headers=authorization(admin))
    assert response.status_code == 400
    assert client.get(PUBLIC_URL).json() == []
    assert client.get(f"{ADMIN_URL}/{approved['id']}", headers=authorization(admin)).json()["status"] == "APPROVED"


def test_invalid_prediction_and_mismatched_location_are_rejected(
    client, admin, location, location_factory, prediction_factory, session_factory,
):
    assert client.post(f"{ADMIN_URL}/from-prediction/999999", headers=authorization(admin)).status_code == 404
    unknown = client.post(ADMIN_URL, headers=authorization(admin), json={
        "location_id": location.id, "prediction_id": 999999, "severity": "HIGH", "message": "Test-only draft",
    })
    assert unknown.status_code == 404
    other = location_factory(name="TEST ONLY — other location")
    prediction = prediction_factory()
    mismatch = client.post(ADMIN_URL, headers=authorization(admin), json={
        "location_id": other.id, "prediction_id": prediction.id, "severity": "HIGH", "message": "Test-only draft",
    })
    assert mismatch.status_code == 400
    with session_factory() as db:
        db.add(Alert(
            location_id=other.id, prediction_id=prediction.id, severity=RiskLevel.HIGH,
            source=AlertSource.AI_RECOMMENDATION, message="Test-only mismatched reference",
        ))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_automatic_creation_for_inactive_location_is_rejected(
    client, admin, location_factory, prediction_factory,
):
    inactive = location_factory(active=False)
    prediction = prediction_factory(location_id=inactive.id)
    assert client.post(f"{ADMIN_URL}/from-prediction/{prediction.id}", headers=authorization(admin)).status_code == 400


@pytest.mark.parametrize("body", [
    {"message": ""}, {"message": "   "}, {"message": "x" * 4001}, {"severity": "EXTREME"},
    {"status": "APPROVED"}, {"approved_by_user_id": 999},
])
def test_manual_alert_payload_validation_blocks_blank_values_and_workflow_bypass(client, admin, location, body):
    response = client.post(ADMIN_URL, headers=authorization(admin), json={
        "location_id": location.id, "severity": "HIGH", "message": "Test-only draft", **body,
    })
    assert response.status_code == 422


@pytest.mark.parametrize("body", [{}, {"message": None}, {"severity": None}, {"status": "APPROVED"}])
def test_edit_requires_explicit_valid_changes(client, admin, location, body):
    alert = manual_alert(client, admin, location.id)
    assert client.patch(f"{ADMIN_URL}/{alert['id']}", headers=authorization(admin), json=body).status_code == 422


def test_admin_list_defaults_to_pending_and_supports_status_filter(client, admin, location):
    pending = manual_alert(client, admin, location.id)
    rejected = manual_alert(client, admin, location.id)
    client.patch(f"{ADMIN_URL}/{rejected['id']}/reject", headers=authorization(admin))
    assert [item["id"] for item in client.get(ADMIN_URL, headers=authorization(admin)).json()] == [pending["id"]]
    assert [item["id"] for item in client.get(ADMIN_URL + "?status=REJECTED", headers=authorization(admin)).json()] == [rejected["id"]]
    assert client.get(ADMIN_URL + "?status=UNKNOWN", headers=authorization(admin)).status_code == 422


def test_alert_not_found_returns_404(client, admin):
    assert client.get(f"{ADMIN_URL}/999999", headers=authorization(admin)).status_code == 404
    assert client.patch(f"{ADMIN_URL}/999999/approve", headers=authorization(admin)).status_code == 404


def test_notification_hook_failure_does_not_undo_saved_approval(client, admin, location, monkeypatch):
    alert = manual_alert(client, admin, location.id)

    def fail(_alert):
        raise RuntimeError("test-only hook failure")

    monkeypatch.setattr(notification_service, "notify_users_for_approved_alert", fail)
    response = client.patch(f"{ADMIN_URL}/{alert['id']}/approve", headers=authorization(admin))
    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"
    assert len(client.get(PUBLIC_URL).json()) == 1


def test_failed_approval_commit_rolls_back_and_never_calls_notification_hook(
    client, admin, location, session_factory, monkeypatch,
):
    alert = manual_alert(client, admin, location.id)
    calls = []
    monkeypatch.setattr(notification_service, "notify_users_for_approved_alert", lambda item: calls.append(item.id))

    def fail_commit(_db):
        raise SQLAlchemyError("test-only internal details must not reach client")

    monkeypatch.setattr(Session, "commit", fail_commit)
    response = client.patch(f"{ADMIN_URL}/{alert['id']}/approve", headers=authorization(admin))
    assert response.status_code == 500
    assert response.json() == {"detail": "Unable to process alert request"}
    assert calls == []
    with session_factory() as db:
        stored = db.get(Alert, alert["id"])
        assert stored.status == AlertStatus.PENDING
        assert stored.approved_at is None


def test_public_database_failure_returns_safe_error(client, monkeypatch):
    def fail(_db, **_kwargs):
        raise alert_service.AlertServiceError("test-only internal database details")
    monkeypatch.setattr(alert_service, "get_public_alerts", fail)
    response = client.get(PUBLIC_URL)
    assert response.status_code == 500
    assert response.json() == {"detail": "Unable to process alert request"}


def test_approval_sets_expiry_window_from_configured_ttl(client, admin, location):
    alert = manual_alert(client, admin, location.id)
    approved = client.patch(f"{ADMIN_URL}/{alert['id']}/approve", headers=authorization(admin)).json()
    assert approved["expires_at"].endswith("Z")
    approved_at = datetime.fromisoformat(approved["approved_at"].replace("Z", "+00:00"))
    expires_at = datetime.fromisoformat(approved["expires_at"].replace("Z", "+00:00"))
    assert timedelta(hours=23, minutes=59) <= expires_at - approved_at <= timedelta(hours=24, minutes=1)


def test_expired_approved_alert_is_hidden_publicly_but_kept_for_admin(
    client, admin, location, session_factory,
):
    alert = manual_alert(client, admin, location.id)
    client.patch(f"{ADMIN_URL}/{alert['id']}/approve", headers=authorization(admin))
    assert len(client.get(PUBLIC_URL).json()) == 1
    with session_factory() as db:
        stored = db.get(Alert, alert["id"])
        stored.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert client.get(PUBLIC_URL).json() == []
    detail = client.get(f"{ADMIN_URL}/{alert['id']}", headers=authorization(admin))
    assert detail.status_code == 200
    assert detail.json()["status"] == "APPROVED"
    assert detail.json()["expires_at"].endswith("Z")


def test_repeated_same_severity_event_reuses_active_alert(
    client, admin, prediction_factory, session_factory,
):
    first = prediction_factory(risk=RiskLevel.HIGH)
    second = prediction_factory(risk=RiskLevel.HIGH)
    created = client.post(f"{ADMIN_URL}/from-prediction/{first.id}", headers=authorization(admin)).json()
    repeated = client.post(f"{ADMIN_URL}/from-prediction/{second.id}", headers=authorization(admin)).json()
    assert repeated["id"] == created["id"]
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Alert)) == 1


def test_severity_escalation_creates_new_alert_during_cooldown(
    client, admin, prediction_factory, session_factory,
):
    first = prediction_factory(risk=RiskLevel.HIGH)
    second = prediction_factory(risk=RiskLevel.VERY_HIGH)
    created = client.post(f"{ADMIN_URL}/from-prediction/{first.id}", headers=authorization(admin)).json()
    escalated = client.post(f"{ADMIN_URL}/from-prediction/{second.id}", headers=authorization(admin)).json()
    assert escalated["id"] != created["id"]
    assert escalated["severity"] == "VERY_HIGH"
    assert escalated["prediction_id"] == second.id
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Alert)) == 2


def test_cooldown_window_allows_new_alert_after_expiry_of_window(
    client, admin, prediction_factory, session_factory,
):
    first = prediction_factory(risk=RiskLevel.HIGH)
    second = prediction_factory(risk=RiskLevel.HIGH)
    created = client.post(f"{ADMIN_URL}/from-prediction/{first.id}", headers=authorization(admin)).json()
    with session_factory() as db:
        stored = db.get(Alert, created["id"])
        stored.created_at = datetime.now(timezone.utc) - timedelta(hours=7)
        db.commit()
    fresh = client.post(f"{ADMIN_URL}/from-prediction/{second.id}", headers=authorization(admin)).json()
    assert fresh["id"] != created["id"]
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Alert)) == 2


def test_rejected_alert_does_not_block_a_new_recommendation(
    client, admin, prediction_factory, session_factory,
):
    first = prediction_factory(risk=RiskLevel.HIGH)
    second = prediction_factory(risk=RiskLevel.HIGH)
    created = client.post(f"{ADMIN_URL}/from-prediction/{first.id}", headers=authorization(admin)).json()
    assert client.patch(f"{ADMIN_URL}/{created['id']}/reject", headers=authorization(admin)).status_code == 200
    fresh = client.post(f"{ADMIN_URL}/from-prediction/{second.id}", headers=authorization(admin)).json()
    assert fresh["id"] != created["id"]
    assert fresh["status"] == "PENDING"
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Alert)) == 2


def test_suppressed_alert_blocks_non_escalating_recommendation(
    client, admin, prediction_factory, session_factory,
):
    first = prediction_factory(risk=RiskLevel.HIGH)
    second = prediction_factory(risk=RiskLevel.HIGH)
    created = client.post(f"{ADMIN_URL}/from-prediction/{first.id}", headers=authorization(admin)).json()
    assert client.patch(f"{ADMIN_URL}/{created['id']}/suppress", headers=authorization(admin), json={
        "reason": "Test-only withdrawal",
    }).status_code == 200
    repeated = client.post(f"{ADMIN_URL}/from-prediction/{second.id}", headers=authorization(admin)).json()
    assert repeated["id"] == created["id"]
    assert repeated["status"] == "SUPPRESSED"
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Alert)) == 1


def test_expired_alert_does_not_block_a_new_recommendation(
    client, admin, prediction_factory, session_factory,
):
    first = prediction_factory(risk=RiskLevel.HIGH)
    second = prediction_factory(risk=RiskLevel.HIGH)
    created = client.post(f"{ADMIN_URL}/from-prediction/{first.id}", headers=authorization(admin)).json()
    client.patch(f"{ADMIN_URL}/{created['id']}/approve", headers=authorization(admin))
    with session_factory() as db:
        stored = db.get(Alert, created["id"])
        stored.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    fresh = client.post(f"{ADMIN_URL}/from-prediction/{second.id}", headers=authorization(admin)).json()
    assert fresh["id"] != created["id"]
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Alert)) == 2


def test_manual_alert_is_not_blocked_by_ai_cooldown(
    client, admin, prediction_factory, session_factory,
):
    prediction = prediction_factory(risk=RiskLevel.HIGH)
    client.post(f"{ADMIN_URL}/from-prediction/{prediction.id}", headers=authorization(admin))
    manual = manual_alert(client, admin, prediction.location_id)
    assert manual["status"] == "PENDING"
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Alert)) == 2
