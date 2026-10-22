"""Flush-only isolated equivalent of the operational pending-alert transaction."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.models.synthetic import SyntheticAlert, SyntheticPrediction
from app.models.user import User, UserRole, AccountStatus


def create_pending(db, prediction, actor_id):
    if not get_settings().synthetic_demo_enabled:
        return None
    actor = db.get(User, actor_id) if actor_id is not None else None
    if actor is None or not actor.is_active or actor.role != UserRole.MET_ADMIN or actor.status != AccountStatus.APPROVED:
        raise HTTPException(403, "An approved MET administrator must initiate synthetic review")
    stored = db.scalar(select(SyntheticPrediction).where(SyntheticPrediction.id == prediction.id).with_for_update())
    if stored is None:
        raise ValueError("Save and flush the synthetic prediction first")
    if stored.risk_category not in ("HIGH", "VERY_HIGH"):
        return None
    def existing():
        return db.scalar(select(SyntheticAlert).where(SyntheticAlert.prediction_id == stored.id))
    alert = existing()
    if alert:
        return alert
    try:
        with db.begin_nested():
            alert = SyntheticAlert(prediction_id=stored.id, status="PENDING", created_by=actor.id)
            db.add(alert)
            db.flush()
    except IntegrityError:
        alert = existing()
        if alert is None:
            raise
    return alert
