"""All personal resources derive their owner from the authenticated account."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, and_, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.session import get_db as base_get_db
from app.models import Location, User, Alert
from app.models.notification import SavedLocation, NotificationPreference, NotificationOutbox, NotificationAttempt
from app.services import notification_outbox as service

router = APIRouter(prefix="/api/me", tags=["saved locations and notifications"])


def get_db(db: Session = Depends(base_get_db)):
    try:
        yield db
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(503, "Unable to process notification request; please retry") from error


class PreferenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    browser_enabled: bool = Field(strict=True)


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=36, max_length=36)
    outcome: Literal["DELIVERED", "FAILED"]
    error: str | None = Field(default=None, max_length=500)


class ClaimCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=36, max_length=36)


@router.get("/subscriptions")
def subscriptions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(select(Location).join(SavedLocation).where(SavedLocation.user_id == user.id).order_by(Location.name))
    return [{"id": row.id, "name": row.name, "is_active": row.is_active} for row in rows]


@router.put("/subscriptions/{location_id}")
def subscribe(location_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    service.lock_user(db, user.id)
    location = db.get(Location, location_id)
    if location is None:
        raise HTTPException(404, "Location not found")
    if not location.is_active:
        raise HTTPException(409, "Location is inactive")
    if db.get(SavedLocation, (user.id, location_id)) is None:
        db.add(SavedLocation(user_id=user.id, location_id=location_id))
    db.commit()
    return {"id": location.id, "name": location.name, "is_active": location.is_active}


@router.delete("/subscriptions/{location_id}", status_code=204)
def unsubscribe(location_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    service.lock_user(db, user.id)
    saved = db.get(SavedLocation, (user.id, location_id))
    if saved is not None:
        db.delete(saved)
    service.cancel(db, user.id, location_id)
    db.commit()
    return Response(status_code=204)


@router.get("/notification-preferences")
def preferences(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pref = db.get(NotificationPreference, user.id)
    return {"browser_enabled": pref.browser_enabled if pref else False,
            "delivery_enabled": get_settings().browser_delivery_enabled}


@router.put("/notification-preferences")
def save_preferences(data: PreferenceInput, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    service.lock_user(db, user.id)
    pref = db.get(NotificationPreference, user.id)
    if pref is None:
        pref = NotificationPreference(user_id=user.id)
        db.add(pref)
    pref.browser_enabled = data.browser_enabled
    if not data.browser_enabled:
        service.cancel(db, user.id)
    db.commit()
    return preferences(db, user)


def notification_json(db, row):
    alert = db.get(Alert, row.alert_id)
    return {"id": row.id, "alert_id": row.alert_id, "status": row.status,
            "location": alert.location.name, "message": alert.message, "is_demo": alert.is_demo,
            "created_at": service.utc(row.created_at),
            "delivered_at": service.utc(row.delivered_at) if row.delivered_at else None,
            "attempts": row.attempts, "last_error": row.last_error,
            "next_attempt_at": service.utc(row.next_attempt_at) if row.next_attempt_at else None}


@router.get("/notifications")
def notifications(pending: bool = False, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(NotificationOutbox).where(NotificationOutbox.user_id == user.id)
    if pending:
        query = query.where(or_(NotificationOutbox.status == "PENDING", and_(
            NotificationOutbox.status == "FAILED", NotificationOutbox.attempts < service.MAX_ATTEMPTS)),
            or_(NotificationOutbox.next_attempt_at.is_(None), NotificationOutbox.next_attempt_at <= service.now()),
            or_(NotificationOutbox.claimed_until.is_(None), NotificationOutbox.claimed_until <= service.now()))
    rows = db.scalars(query.order_by(NotificationOutbox.id.asc() if pending else NotificationOutbox.id.desc()).offset(offset).limit(limit))
    return [notification_json(db, row) for row in rows]


@router.get("/notifications/{notification_id}/attempts")
def attempts(notification_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.get(NotificationOutbox, notification_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "Notification not found")
    return [{"started_at": service.utc(a.started_at), "finished_at": service.utc(a.finished_at) if a.finished_at else None,
             "outcome": a.outcome, "error": a.error} for a in db.scalars(select(NotificationAttempt)
             .where(NotificationAttempt.notification_id == row.id).order_by(NotificationAttempt.started_at))]


@router.post("/notifications/{notification_id}/claim")
def claim(notification_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return service.claim(db, user.id, notification_id)


@router.post("/notifications/{notification_id}/receipt")
def receipt(notification_id: int, data: Receipt, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = service.acknowledge(db, user.id, notification_id, data.token, data.outcome, data.error)
    return notification_json(db, row)


@router.post("/notifications/{notification_id}/check")
def check(notification_id: int, data: ClaimCheck, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row, alert, recipient = service.owned(db, user.id, notification_id)
    if (not get_settings().browser_delivery_enabled or row.status != "PENDING"
            or row.claim_token != data.token or row.claimed_until is None
            or service.utc(row.claimed_until) <= service.now()):
        raise HTTPException(409, "Delivery claim is no longer valid")
    if not service.eligible(db, recipient, alert):
        row.status, row.last_error = "CANCELLED", "Alert or recipient is no longer eligible"
        db.commit()
        raise HTTPException(409, row.last_error)
    return {"deliverable": True}
