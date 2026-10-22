"""Alert inputs and deliberately separate administrator/public response schemas."""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.alert import AlertSource, AlertStatus
from app.models.risk import RiskLevel


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    # SQLite fixtures strip timezone information; persisted timestamps are defined as UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class AlertInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ManualAlertCreate(AlertInput):
    location_id: int = Field(gt=0)
    prediction_id: int | None = Field(default=None, gt=0)
    severity: RiskLevel
    message: str = Field(min_length=1, max_length=4000)


class AlertUpdate(AlertInput):
    message: str | None = Field(default=None, min_length=1, max_length=4000)
    severity: RiskLevel | None = None

    @field_validator("message", "severity")
    @classmethod
    def disallow_explicit_null(cls, value: str | RiskLevel | None) -> str | RiskLevel:
        if value is None:
            raise ValueError("Updated fields cannot be null")
        return value

    @model_validator(mode="after")
    def require_change(self) -> "AlertUpdate":
        if not self.model_fields_set:
            raise ValueError("Provide a message or severity to update")
        return self


class AlertSuppressionRequest(AlertInput):
    reason: str = Field(min_length=1, max_length=1000)


class AlertClosureRequest(AlertInput):
    reason: str = Field(min_length=1, max_length=1000)


class LocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class AdminLocationResponse(LocationResponse):
    is_active: bool


class PredictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    risk_level: RiskLevel
    flood_probability: float
    confidence_percent: float
    model_version: str
    is_sample: bool
    predicted_at: datetime

    @field_validator("predicted_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return _utc(value)


class AlertResponse(BaseModel):
    """Public information only: no creator/reviewer IDs or internal suppression reasons."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    is_demo: bool
    location_id: int
    location: LocationResponse
    prediction_id: int | None
    prediction: PredictionResponse | None
    severity: RiskLevel
    status: AlertStatus
    source: AlertSource
    message: str
    created_at: datetime
    approved_at: datetime | None
    expires_at: datetime | None

    @field_validator("created_at", "approved_at", "expires_at")
    @classmethod
    def utc_timestamp(cls, value: datetime | None) -> datetime | None:
        return _utc(value)


class AlertDetailResponse(AlertResponse):
    """Administrator-only view with location state and review audit information."""

    location: AdminLocationResponse
    created_by_user_id: int | None
    updated_by_user_id: int | None
    updated_at: datetime | None
    approved_by_user_id: int | None
    rejected_by_user_id: int | None
    rejected_at: datetime | None
    suppression_reason: str | None
    suppressed_by_user_id: int | None
    suppressed_at: datetime | None
    acknowledged_by_user_id: int | None
    acknowledged_at: datetime | None
    closed_by_user_id: int | None
    closed_at: datetime | None
    closure_reason: str | None

    @field_validator("updated_at", "rejected_at", "suppressed_at", "acknowledged_at", "closed_at")
    @classmethod
    def utc_audit_timestamp(cls, value: datetime | None) -> datetime | None:
        return _utc(value)
