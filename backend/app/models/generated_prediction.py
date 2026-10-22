"""Provenance for V1 weather inference; all predictions remain synthetic-only."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class V1WeatherProfile(Base):
    __tablename__ = "v1_weather_profiles"
    source: Mapped[str] = mapped_column(String(100), primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), primary_key=True)
    dataset_version: Mapped[str] = mapped_column(ForeignKey("synthetic_datasets.version"))
    attributes: Mapped[dict] = mapped_column(JSON)
    provenance: Mapped[dict] = mapped_column(JSON)


class GeneratedPredictionProvenance(Base):
    __tablename__ = "generated_prediction_provenance"
    prediction_id: Mapped[int] = mapped_column(ForeignKey("synthetic_predictions.id"), primary_key=True)
    source: Mapped[str] = mapped_column(String(100))
    inputs: Mapped[dict] = mapped_column(JSON)
    input_sha256: Mapped[str] = mapped_column(String(64))
    model_sha256: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
