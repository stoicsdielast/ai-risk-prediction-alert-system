"""Storage/read contract; never fills missing measurements or calls prediction/alerts."""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.location import Location
from app.models.weather import DemoWeatherObservation, WeatherObservation
from app.schemas.weather import MEASUREMENTS, RESEARCH_NOTICE, WeatherCreate, WeatherResponse


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def model_for(synthetic=False):
    return DemoWeatherObservation if synthetic else WeatherObservation


def require_location(db, location_id, *, writing=False):
    location = db.get(Location, location_id)
    if location is None:
        raise HTTPException(404, "Unknown monitored location")
    if writing and not location.is_active:
        raise HTTPException(409, "Location is inactive")
    return location


def insert_observation(db: Session, data: WeatherCreate, submitted_by=None):
    require_location(db, data.location_id, writing=True)
    model = model_for(data.source_type == "synthetic")
    identity = (model.location_id == data.location_id, model.source == data.source,
                model.source_type == data.source_type, model.observed_at == data.observed_at)

    def existing():
        row = db.scalar(select(model).where(*identity))
        if row is not None:
            for key, value in data.model_dump().items():
                stored = utc(row.observed_at) if key == "observed_at" else getattr(row, key)
                if stored != value:
                    raise HTTPException(409, "Observation identity already exists with different measurements")
        return row

    row = existing()
    if row is not None:
        return row, False
    try:
        with db.begin_nested():
            row = model(**data.model_dump(), received_at=datetime.now(timezone.utc), submitted_by=submitted_by)
            db.add(row)
            db.flush()
    except IntegrityError:
        row = existing()
        if row is None:
            raise
        return row, False
    return row, True


def present(row):
    age = max(0, (datetime.now(timezone.utc) - utc(row.observed_at)).total_seconds())
    keys = ["id", "location_id", "source", "source_type", "rainfall_period_minutes",
            "upstream_rainfall_period_minutes", "gauge_datum", *MEASUREMENTS]
    return WeatherResponse(
        **{key: getattr(row, key) for key in keys}, observed_at=utc(row.observed_at),
        received_at=utc(row.received_at), age_seconds=age,
        stale=age > get_settings().weather_freshness_minutes * 60,
        missing_fields=[key for key in MEASUREMENTS if getattr(row, key) is None],
        notice=RESEARCH_NOTICE if row.source_type == "synthetic" else None,
    )


def observations(db, location_id, *, synthetic=False, source=None, start=None, end=None, limit=100, offset=0):
    require_location(db, location_id)
    model = model_for(synthetic)
    query = select(model).where(model.location_id == location_id)
    if source:
        query = query.where(model.source == source)
    if start:
        query = query.where(model.observed_at >= start)
    if end:
        query = query.where(model.observed_at <= end)
    return list(db.scalars(query.order_by(model.observed_at.desc(), model.id.desc()).limit(limit).offset(offset)))
