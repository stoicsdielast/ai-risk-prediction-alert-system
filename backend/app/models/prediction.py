"""Persistence contract for future prediction ingestion; no predictions are generated here."""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.location import Location
from app.models.risk import RiskLevel, risk_level_enum


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (
        UniqueConstraint("id", "location_id", name="uq_prediction_id_location"),
        CheckConstraint(
            "flood_probability >= 0 AND flood_probability <= 1",
            name="ck_prediction_probability",
        ),
        CheckConstraint("length(trim(model_version)) > 0", name="ck_prediction_model_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    risk_level: Mapped[RiskLevel] = mapped_column(risk_level_enum, nullable=False)
    flood_probability: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String(255), nullable=False)
    predicted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
    )
    # True for hand-written demo values loaded by app.db.seed_locations. Sample
    # rows are for testing the map and are never real model output.
    is_sample: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"),
    )
    location: Mapped[Location] = relationship()

    @property
    def confidence_percent(self) -> float:
        """Compatibility with standalone inference: P(flood) * 100, not calibration confidence."""
        return self.flood_probability * 100
