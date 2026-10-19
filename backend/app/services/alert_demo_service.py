"""Opt-in workflow fixtures. These simulate AI output and never claim model skill."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.alert import Alert, AlertStatus
from app.models.location import Location
from app.models.prediction import ALERT_DEMO_MODEL_PREFIX, Prediction
from app.models.risk import RiskLevel
from app.services.alert_service import (
    InvalidAlertDataError, _active_location, _database_operation, create_alert_from_prediction,
)

SCENARIOS = {
    "nausori-high": ("nausori", RiskLevel.HIGH, 0.82),
    "labasa-very-high": ("labasa", RiskLevel.VERY_HIGH, 0.94),
}


@_database_operation
def create_demo_alert(db: Session, scenario: str) -> Alert:
    if not get_settings().alert_demo_enabled:
        raise InvalidAlertDataError("Alert demonstrations are disabled")
    if scenario not in SCENARIOS:
        raise InvalidAlertDataError("Unknown demonstration scenario")
    slug, risk, probability = SCENARIOS[scenario]
    location = db.scalar(select(Location).where(Location.slug == slug))
    if location is None:
        raise InvalidAlertDataError("Run python -m app.db.seed_locations before using alert demonstrations")
    # Serialize scenario creation at the existing location without altering its data.
    location = _active_location(db, location.id)
    version = ALERT_DEMO_MODEL_PREFIX + scenario
    existing = db.scalar(select(Alert).join(Prediction, Alert.prediction_id == Prediction.id).where(
        Alert.location_id == location.id, Prediction.model_version == version,
        Prediction.is_sample.is_(True), Alert.status.in_([AlertStatus.PENDING, AlertStatus.APPROVED]),
    ).order_by(Alert.id.desc()))
    if existing is not None:
        db.commit()
        return existing
    prediction = Prediction(
        location_id=location.id, risk_level=risk, flood_probability=probability,
        model_version=version, is_sample=True,
    )
    db.add(prediction)
    db.flush()
    alert = create_alert_from_prediction(db, prediction)
    db.commit()
    return alert
