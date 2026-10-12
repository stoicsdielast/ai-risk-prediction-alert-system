from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RiskLevel(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class PredictionSource(str, Enum):
    # Hand-written demo values for testing the map. Never a real forecast.
    SAMPLE = "SAMPLE"
    # Reserved for output from the flood-risk model once it exists.
    MODEL = "MODEL"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RiskPrediction(Base):
    __tablename__ = "risk_predictions"
    __table_args__ = (
        CheckConstraint(
            "confidence_percent >= 0 AND confidence_percent <= 100",
            name="ck_risk_predictions_confidence_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    risk_level: Mapped[RiskLevel] = mapped_column(
        SqlEnum(RiskLevel, name="risk_level"),
        nullable=False,
    )
    confidence_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(String(1000), nullable=False)
    source: Mapped[PredictionSource] = mapped_column(
        SqlEnum(PredictionSource, name="prediction_source"),
        nullable=False,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
