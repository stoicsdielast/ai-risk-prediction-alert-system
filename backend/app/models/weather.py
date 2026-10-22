"""Genuine measurements and research/demo measurements use separate tables."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ObservationColumns:
    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(100))
    source_type: Mapped[str] = mapped_column(String(20))
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    rainfall_mm: Mapped[float | None] = mapped_column(Float)
    rainfall_period_minutes: Mapped[int | None] = mapped_column(Integer)
    temperature_c: Mapped[float | None] = mapped_column(Float)
    humidity_pct: Mapped[float | None] = mapped_column(Float)
    pressure_hpa: Mapped[float | None] = mapped_column(Float)
    wind_speed_mps: Mapped[float | None] = mapped_column(Float)
    wind_direction_deg: Mapped[float | None] = mapped_column(Float)
    river_level_m: Mapped[float | None] = mapped_column(Float)
    river_discharge_m3s: Mapped[float | None] = mapped_column(Float)
    soil_moisture_pct: Mapped[float | None] = mapped_column(Float)
    upstream_rainfall_mm: Mapped[float | None] = mapped_column(Float)
    upstream_rainfall_period_minutes: Mapped[int | None] = mapped_column(Integer)
    coastal_tide_m: Mapped[float | None] = mapped_column(Float)
    gauge_datum: Mapped[str | None] = mapped_column(String(100))


class WeatherObservation(ObservationColumns, Base):
    __tablename__ = "weather_observations"
    __table_args__ = (
        UniqueConstraint("location_id", "source_type", "source", "observed_at", name="uq_weather_identity"),
        CheckConstraint("source_type IN ('manual', 'provider')", name="ck_weather_genuine"),
    )


class DemoWeatherObservation(ObservationColumns, Base):
    __tablename__ = "demo_weather_observations"
    __table_args__ = (
        UniqueConstraint("location_id", "source_type", "source", "observed_at", name="uq_demo_weather_identity"),
        CheckConstraint("source_type = 'synthetic'", name="ck_weather_synthetic"),
    )
