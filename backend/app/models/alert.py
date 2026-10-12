"""Persistent alerts with controlled lifecycle, references, and administrator audit fields."""

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    CheckConstraint, DateTime, Enum as SqlEnum, ForeignKey, ForeignKeyConstraint,
    Index, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.location import Location
from app.models.prediction import Prediction
from app.models.risk import RiskLevel, risk_level_enum


class AlertStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPPRESSED = "SUPPRESSED"


class AlertSource(str, Enum):
    AI_RECOMMENDATION = "AI_RECOMMENDATION"
    MET_OFFICIAL = "MET_OFFICIAL"


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        # One alert per location/prediction across all states; NULL permits multiple manual alerts.
        UniqueConstraint("location_id", "prediction_id", name="uq_alert_location_prediction"),
        ForeignKeyConstraint(
            ["prediction_id", "location_id"], ["predictions.id", "predictions.location_id"],
            name="fk_alert_prediction_location", ondelete="RESTRICT",
        ),
        CheckConstraint("length(trim(message)) > 0", name="ck_alert_message"),
        CheckConstraint(
            "source != 'AI_RECOMMENDATION' OR prediction_id IS NOT NULL",
            name="ck_ai_alert_prediction",
        ),
        CheckConstraint(
            "source != 'MET_OFFICIAL' OR created_by_user_id IS NOT NULL",
            name="ck_manual_alert_creator",
        ),
        CheckConstraint(
            "status != 'APPROVED' OR (approved_by_user_id IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_approved_alert_audit",
        ),
        CheckConstraint(
            "status != 'REJECTED' OR (rejected_by_user_id IS NOT NULL AND rejected_at IS NOT NULL)",
            name="ck_rejected_alert_audit",
        ),
        CheckConstraint(
            "status != 'SUPPRESSED' OR (suppressed_by_user_id IS NOT NULL AND suppressed_at IS NOT NULL "
            "AND suppression_reason IS NOT NULL AND length(trim(suppression_reason)) > 0)",
            name="ck_suppressed_alert_audit",
        ),
        Index("ix_alert_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False,
    )
    prediction_id: Mapped[int | None] = mapped_column(nullable=True)
    severity: Mapped[RiskLevel] = mapped_column(risk_level_enum, nullable=False)
    status: Mapped[AlertStatus] = mapped_column(
        SqlEnum(AlertStatus, name="alert_status", create_constraint=True, validate_strings=True),
        nullable=False, default=AlertStatus.PENDING, server_default=AlertStatus.PENDING.value,
    )
    source: Mapped[AlertSource] = mapped_column(
        SqlEnum(AlertSource, name="alert_source", create_constraint=True, validate_strings=True),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
    )
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suppression_reason: Mapped[str | None] = mapped_column(String(1000))
    suppressed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    suppressed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    location: Mapped[Location] = relationship(foreign_keys=[location_id], lazy="selectin")
    prediction: Mapped[Prediction | None] = relationship(
        primaryjoin="Alert.prediction_id == Prediction.id", foreign_keys=[prediction_id],
        viewonly=True, lazy="selectin",
    )
