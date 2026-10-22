"""Synthetic-only persistence, isolated from operational predictions/alerts."""
from datetime import datetime, timezone
from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class SyntheticDataset(Base):
    __tablename__ = "synthetic_datasets"
    version: Mapped[str] = mapped_column(String(100), primary_key=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SyntheticObservation(Base):
    __tablename__ = "synthetic_observations"
    dataset_version: Mapped[str] = mapped_column(ForeignKey("synthetic_datasets.version"), primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, index=True)
    values: Mapped[dict] = mapped_column(JSON, nullable=False)


class SyntheticPrediction(Base):
    __tablename__ = "synthetic_predictions"
    __table_args__ = (
        UniqueConstraint("dataset_version", "location_id", "observed_at", "model_version", name="uq_synthetic_prediction"),
        CheckConstraint("probability >= 0 AND probability <= 1", name="ck_synthetic_probability"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_version: Mapped[str] = mapped_column(ForeignKey("synthetic_datasets.version"), nullable=False)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    model_version: Mapped[str] = mapped_column(String(150), nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    risk_category: Mapped[str] = mapped_column(String(20), nullable=False)


class SyntheticAlert(Base):
    __tablename__ = "synthetic_alerts"
    __table_args__ = (CheckConstraint("status IN ('PENDING','APPROVED','REJECTED')", name="ck_synthetic_alert_status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("synthetic_predictions.id"), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
