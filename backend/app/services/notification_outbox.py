"""Transactional enqueue and leased, authenticated browser delivery. No push provider."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import get_settings
from app.models import Alert, AlertStatus, Location, User, AccountStatus
from app.models.notification import SavedLocation, NotificationPreference, NotificationOutbox, NotificationAttempt
from app.schemas.alert import AlertResponse

MAX_ATTEMPTS = 5


def now():
    return datetime.now(timezone.utc)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def lock_user(db, user_id):
    return db.scalar(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True))


def alert_available(alert):
    if not isinstance(alert, Alert) or alert.status != AlertStatus.APPROVED or not alert.location.is_active:
        return False
    if alert.expires_at is not None and utc(alert.expires_at) <= now():
        return False
    if alert.prediction is not None and alert.prediction.is_sample:
        return get_settings().alert_demo_enabled and alert.is_demo
    return True


def eligible(db, user, alert):
    pref = db.get(NotificationPreference, user.id, populate_existing=True)
    return (user.is_active and user.status == AccountStatus.APPROVED
            and pref is not None and pref.browser_enabled
            and db.get(SavedLocation, (user.id, alert.location_id)) is not None
            and alert_available(alert))


def enqueue(db, alert):
    """Caller owns approval transaction and alert lock; never accepts SyntheticAlert IDs."""
    if not alert_available(alert):
        return
    users = list(db.scalars(select(SavedLocation.user_id).where(
        SavedLocation.location_id == alert.location_id).order_by(SavedLocation.user_id)))
    for user_id in users:
        user = lock_user(db, user_id)
        if not eligible(db, user, alert):
            continue
        existing = db.scalar(select(NotificationOutbox.id).where(
            NotificationOutbox.user_id == user_id, NotificationOutbox.alert_id == alert.id))
        if existing is None:
            db.add(NotificationOutbox(user_id=user_id, alert_id=alert.id))
    db.flush()


def cancel(db, user_id, location_id=None):
    query = select(NotificationOutbox).where(NotificationOutbox.user_id == user_id,
        NotificationOutbox.status.in_(["PENDING", "FAILED"]))
    if location_id is not None:
        query = query.join(Alert).where(Alert.location_id == location_id)
    for row in db.scalars(query):
        row.status = "CANCELLED"
        row.last_error = "Notification preference or subscription removed"


def owned(db, user_id, notification_id):
    row = db.scalar(select(NotificationOutbox).where(
        NotificationOutbox.id == notification_id, NotificationOutbox.user_id == user_id))
    if row is None:
        raise HTTPException(404, "Notification not found")
    # Same ordering as approval: alert -> user -> notification.
    alert = db.scalar(select(Alert).where(Alert.id == row.alert_id).with_for_update().execution_options(populate_existing=True))
    user = lock_user(db, user_id)
    row = db.scalar(select(NotificationOutbox).where(NotificationOutbox.id == row.id)
                    .with_for_update().execution_options(populate_existing=True))
    return row, alert, user


def claim(db, user_id, notification_id):
    if not get_settings().browser_delivery_enabled:
        raise HTTPException(409, "Browser delivery is disabled by the operator")
    row, alert, user = owned(db, user_id, notification_id)
    if row.status in ("DELIVERED", "CANCELLED"):
        raise HTTPException(409, "Notification is already completed")
    if not eligible(db, user, alert):
        row.status, row.last_error = "CANCELLED", "Alert or recipient is no longer eligible"
        db.commit()
        raise HTTPException(409, row.last_error)
    stamp = now()
    if row.claimed_until and utc(row.claimed_until) > stamp:
        raise HTTPException(409, "Notification already claimed")
    if row.next_attempt_at and utc(row.next_attempt_at) > stamp:
        raise HTTPException(409, "Retry backoff has not elapsed")
    if row.claim_token:
        previous = db.get(NotificationAttempt, row.claim_token)
        if previous and previous.outcome == "PENDING":
            previous.outcome, previous.finished_at, previous.error = "FAILED", stamp, "Delivery acknowledgement timed out"
            row.last_error = previous.error
    if row.attempts >= MAX_ATTEMPTS:
        row.status = "FAILED"
        db.commit()
        raise HTTPException(409, "Retry limit reached")
    row.claim_token = str(uuid4())
    row.claimed_until = stamp + timedelta(seconds=90)
    row.attempts += 1
    row.status = "PENDING"
    db.add(NotificationAttempt(token=row.claim_token, notification_id=row.id))
    db.commit()
    return {"id": row.id, "token": row.claim_token, "alert": AlertResponse.model_validate(alert),
            "expires_at": row.claimed_until}


def acknowledge(db, user_id, notification_id, token, outcome, error):
    row, alert, user = owned(db, user_id, notification_id)
    if token != row.claim_token:
        raise HTTPException(409, "Stale delivery claim")
    attempt = db.get(NotificationAttempt, token)
    if attempt is None:
        raise HTTPException(409, "Unknown delivery claim")
    if attempt.outcome != "PENDING":
        if attempt.outcome == outcome:
            return row
        raise HTTPException(409, "Delivery result already recorded")
    stamp = now()
    if not eligible(db, user, alert) or row.status == "CANCELLED":
        row.status = "CANCELLED"
        row.last_error = "Alert or recipient is no longer eligible"
        attempt.outcome, attempt.error = "CANCELLED", row.last_error
    elif row.claimed_until is None or utc(row.claimed_until) <= stamp:
        raise HTTPException(409, "Delivery claim expired")
    else:
        attempt.outcome = outcome
        row.status = outcome
        if outcome == "DELIVERED":
            row.delivered_at = stamp
        else:
            attempt.error = error or "Browser delivery failed"
            row.last_error = attempt.error
            row.next_attempt_at = stamp + timedelta(seconds=min(30 * 2 ** (row.attempts - 1), 900))
    attempt.finished_at = stamp
    row.claimed_until = None
    db.commit()
    return row
