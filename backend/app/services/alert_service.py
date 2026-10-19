"""Alert business rules, transaction boundaries, and reviewed public visibility."""

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from functools import wraps

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings

from app.models.alert import Alert, AlertSource, AlertStatus
from app.models.location import Location
from app.models.prediction import ALERT_DEMO_MODEL_PREFIX, Prediction
from app.models.risk import RiskLevel
from app.models.user import User
from app.schemas.alert import AlertSuppressionRequest, AlertUpdate, ManualAlertCreate
from app.services import notification_service

logger = logging.getLogger(__name__)

HIGH_RISK_LEVELS = frozenset({RiskLevel.HIGH, RiskLevel.VERY_HIGH})
ALLOWED_TRANSITIONS = {
    AlertStatus.PENDING: frozenset({AlertStatus.APPROVED, AlertStatus.REJECTED, AlertStatus.SUPPRESSED}),
    AlertStatus.APPROVED: frozenset({AlertStatus.SUPPRESSED}),
    AlertStatus.REJECTED: frozenset(),
    AlertStatus.SUPPRESSED: frozenset(),
}


class AlertBusinessError(Exception):
    """Expected validation/state errors, safe to map to HTTP responses."""


class AlertNotFoundError(AlertBusinessError):
    pass


class LocationNotFoundError(AlertBusinessError):
    pass


class PredictionNotFoundError(AlertBusinessError):
    pass


class InactiveLocationError(AlertBusinessError):
    pass


class InvalidAlertDataError(AlertBusinessError):
    pass


class InvalidAlertStateError(AlertBusinessError):
    pass


class AlertConflictError(AlertBusinessError):
    pass


class AlertServiceError(Exception):
    """Database failure; original details never appear in HTTP responses."""


def _database_operation[T](operation: Callable[..., T]) -> Callable[..., T]:
    @wraps(operation)
    def wrapped(db: Session, *args, **kwargs) -> T:
        try:
            return operation(db, *args, **kwargs)
        except AlertBusinessError:
            db.rollback()
            raise
        except SQLAlchemyError as error:
            db.rollback()
            raise AlertServiceError from error
    return wrapped


def _active_location(db: Session, location_id: int) -> Location:
    location = db.scalar(
        select(Location).where(Location.id == location_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    if location is None:
        raise LocationNotFoundError("Location not found")
    if not location.is_active:
        raise InactiveLocationError("Location is inactive")
    return location


def _prediction(db: Session, prediction_id: int) -> Prediction:
    prediction = db.scalar(
        select(Prediction).where(Prediction.id == prediction_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    if prediction is None:
        raise PredictionNotFoundError("Prediction not found")
    return prediction


def _require_real_prediction(prediction: Prediction) -> None:
    if prediction.is_sample and not (get_settings().alert_demo_enabled and prediction.is_alert_demo):
        raise InvalidAlertDataError("Sample predictions cannot be used for alerts")


def _get_alert(db: Session, alert_id: int, *, lock: bool = False) -> Alert:
    query = select(Alert).where(Alert.id == alert_id).execution_options(populate_existing=True)
    if lock:
        query = query.with_for_update()
    alert = db.scalar(query)
    if alert is None:
        raise AlertNotFoundError("Alert not found")
    return alert


def _existing_alert(db: Session, prediction: Prediction) -> Alert | None:
    return db.scalar(select(Alert).where(
        Alert.location_id == prediction.location_id, Alert.prediction_id == prediction.id,
    ).execution_options(populate_existing=True))


def _duplicate_prediction_alert(error: IntegrityError) -> bool:
    diagnostic = getattr(error.orig, "diag", None)
    if getattr(diagnostic, "constraint_name", None) == "uq_alert_location_prediction":
        return True
    return "alerts.location_id, alerts.prediction_id" in str(error.orig).lower()


def ensure_transition(alert: Alert, target: AlertStatus) -> None:
    if target not in ALLOWED_TRANSITIONS.get(alert.status, frozenset()):
        raise InvalidAlertStateError(
            f"Cannot transition alert from {alert.status.value} to {target.value}"
        )


@_database_operation
def create_alert_from_prediction(db: Session, prediction: Prediction, *, research_actor_id: int | None = None):
    """Flush, but do not commit: caller can persist prediction + alert atomically.

    Pass a saved/flushed Prediction from this session. The persisted row is
    locked/re-read so caller-supplied or stale risk/location values aren't trusted.
    A reviewed historical alert is also reused; retries never revive it.
    """
    # Synthetic rows never enter the operational lookup, constraints or notification hook.
    # Preserve the existing operational contract while sharing the flush-only entrypoint.
    from app.models.synthetic import SyntheticPrediction
    if isinstance(prediction, SyntheticPrediction):
        from app.services.synthetic_alert_service import create_pending
        return create_pending(db, prediction, research_actor_id)
    if prediction.id is None:
        raise InvalidAlertDataError("Save and flush the prediction before creating its alert")
    stored = _prediction(db, prediction.id)
    _require_real_prediction(stored)
    if stored.risk_level not in HIGH_RISK_LEVELS:
        return None
    existing = _existing_alert(db, stored)
    if existing is not None:
        return existing
    location = _active_location(db, stored.location_id)
    alert = Alert(
        location_id=location.id, prediction_id=stored.id,
        severity=stored.risk_level, status=AlertStatus.PENDING,
        source=AlertSource.AI_RECOMMENDATION,
        message=(
            ("DEMO ONLY — simulated prediction; not an official Fiji MET warning. " if stored.is_alert_demo else "") +
            f"AI-generated flood-risk recommendation for {location.name}: "
            f"{stored.risk_level.value.replace('_', ' ').lower()} risk. "
            "This recommendation is for Fiji MET review."
        ),
    )
    try:
        # A savepoint preserves the caller's prediction if another writer wins the insert.
        with db.begin_nested():
            db.add(alert)
            db.flush()
    except IntegrityError as error:
        if _duplicate_prediction_alert(error):
            existing = _existing_alert(db, stored)
            if existing is not None:
                return existing
        raise
    return alert


@_database_operation
def create_alert_for_prediction_id(db: Session, prediction_id: int) -> Alert | None:
    """Admin retry adapter for an already persisted prediction; commits the result."""
    alert = create_alert_from_prediction(db, _prediction(db, prediction_id))
    db.commit()
    return alert


@_database_operation
def create_manual_alert(db: Session, data: ManualAlertCreate, admin: User) -> Alert:
    # Keep the same lock ordering as automatic creation (prediction before location).
    if data.prediction_id is not None:
        prediction = _prediction(db, data.prediction_id)
        _require_real_prediction(prediction)
        if prediction.location_id != data.location_id:
            raise InvalidAlertDataError("Prediction belongs to a different location")
        if _existing_alert(db, prediction) is not None:
            raise AlertConflictError("An alert already exists for this location and prediction")
    location = _active_location(db, data.location_id)
    alert = Alert(
        location_id=location.id, prediction_id=data.prediction_id,
        severity=data.severity, message=data.message,
        source=AlertSource.MET_OFFICIAL, status=AlertStatus.PENDING,
        created_by_user_id=admin.id,
    )
    db.add(alert)
    try:
        db.commit()
    except IntegrityError as error:
        if _duplicate_prediction_alert(error):
            db.rollback()
            raise AlertConflictError("An alert already exists for this location and prediction") from error
        raise
    return alert


@_database_operation
def get_pending_alerts(
    db: Session, status: AlertStatus | None = AlertStatus.PENDING,
    *, offset: int = 0, limit: int = 100,
) -> list[Alert]:
    query = select(Alert)
    if status is not None:
        query = query.where(Alert.status == status)
    return list(db.scalars(query.order_by(Alert.created_at.desc(), Alert.id.desc()).offset(offset).limit(limit)))


@_database_operation
def get_alert(db: Session, alert_id: int) -> Alert:
    return _get_alert(db, alert_id)


@_database_operation
def update_alert(db: Session, alert_id: int, data: AlertUpdate, admin: User) -> Alert:
    alert = _get_alert(db, alert_id, lock=True)
    if alert.status != AlertStatus.PENDING:
        raise InvalidAlertStateError("Only pending alerts can be edited")
    for name, value in data.model_dump(exclude_unset=True).items():
        setattr(alert, name, value)
    alert.updated_by_user_id = admin.id
    alert.updated_at = datetime.now(timezone.utc)
    db.commit()
    return alert


@_database_operation
def approve_alert(db: Session, alert_id: int, admin: User) -> Alert:
    alert = _get_alert(db, alert_id, lock=True)
    ensure_transition(alert, AlertStatus.APPROVED)
    if alert.prediction_id is not None:
        _require_real_prediction(_prediction(db, alert.prediction_id))
    _active_location(db, alert.location_id)
    if not isinstance(alert.message, str) or not alert.message.strip() or len(alert.message) > 4000:
        raise InvalidAlertDataError("Alert requires a nonblank message of at most 4000 characters")
    if alert.severity not in set(RiskLevel):
        raise InvalidAlertDataError("Alert requires a valid severity")
    if alert.source == AlertSource.AI_RECOMMENDATION and alert.prediction_id is None:
        raise InvalidAlertDataError("AI recommendation requires a prediction")
    alert.status = AlertStatus.APPROVED
    alert.approved_by_user_id = admin.id
    alert.approved_at = datetime.now(timezone.utc)
    db.commit()
    # This development hook runs only after successful persistence; it sends nothing.
    try:
        notification_service.notify_users_for_approved_alert(alert)
    except Exception:
        logger.exception("Notification hook failed for approved alert #%s; approval remains saved", alert.id)
    return alert


@_database_operation
def reject_alert(db: Session, alert_id: int, admin: User) -> Alert:
    alert = _get_alert(db, alert_id, lock=True)
    ensure_transition(alert, AlertStatus.REJECTED)
    alert.status = AlertStatus.REJECTED
    alert.rejected_by_user_id = admin.id
    alert.rejected_at = datetime.now(timezone.utc)
    db.commit()
    return alert


@_database_operation
def suppress_alert(
    db: Session, alert_id: int, data: AlertSuppressionRequest, admin: User,
) -> Alert:
    alert = _get_alert(db, alert_id, lock=True)
    ensure_transition(alert, AlertStatus.SUPPRESSED)
    alert.status = AlertStatus.SUPPRESSED
    alert.suppression_reason = data.reason
    alert.suppressed_by_user_id = admin.id
    alert.suppressed_at = datetime.now(timezone.utc)
    db.commit()
    return alert


@_database_operation
def get_public_alerts(db: Session, *, offset: int = 0, limit: int = 100) -> list[Alert]:
    allowed_prediction = ~Alert.prediction.has(Prediction.is_sample.is_(True))
    if get_settings().alert_demo_enabled:
        allowed_prediction = or_(allowed_prediction, Alert.prediction.has(and_(
            Prediction.is_sample.is_(True),
            Prediction.model_version.startswith(ALERT_DEMO_MODEL_PREFIX),
        )))
    return list(db.scalars(
        select(Alert).join(Location, Alert.location_id == Location.id)
        .where(Alert.status == AlertStatus.APPROVED, Location.is_active.is_(True))
        .where(allowed_prediction)
        .order_by(Alert.approved_at.desc(), Alert.id.desc()).offset(offset).limit(limit)
    ))
