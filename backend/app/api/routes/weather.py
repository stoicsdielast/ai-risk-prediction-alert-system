from contextlib import contextmanager
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import AwareDatetime
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import require_met_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.weather import LatestWeather, RESEARCH_NOTICE, WeatherCreate, WeatherResponse, WeatherHistory
from app.services import weather_service as service

router = APIRouter(tags=["weather"])


@contextmanager
def database_errors(db):
    try:
        yield
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(503, "Weather storage temporarily unavailable") from error


@router.post("/api/admin/weather/observations", response_model=WeatherResponse, status_code=201)
def ingest(data: WeatherCreate, response: Response, db: Session = Depends(get_db),
           admin: User = Depends(require_met_admin)):
    with database_errors(db):
        row, created = service.insert_observation(db, data, admin.id)
        db.commit()
        response.status_code = 201 if created else 200
        return service.present(row)


@router.get("/api/weather/latest", response_model=LatestWeather)
def latest(location_id: int = Query(gt=0), dataset: Literal["genuine", "synthetic"] = "genuine",
           source: str | None = Query(default=None, max_length=100), db: Session = Depends(get_db)):
    with database_errors(db):
        rows = service.observations(db, location_id, synthetic=dataset == "synthetic", source=source, limit=1)
        observation = service.present(rows[0]) if rows else None
        return LatestWeather(location_id=location_id, source_type=dataset,
                             notice=RESEARCH_NOTICE if dataset == "synthetic" else None,
                             status="no_data" if observation is None else "stale" if observation.stale else "fresh",
                             observation=observation)


@router.get("/api/weather/observations", response_model=WeatherHistory)
def history(location_id: int = Query(gt=0), dataset: Literal["genuine", "synthetic"] = "genuine",
            source: str | None = Query(default=None, max_length=100),
            start: AwareDatetime | None = None, end: AwareDatetime | None = None,
            limit: int = Query(default=100, ge=1, le=1000), offset: int = Query(default=0, ge=0),
            db: Session = Depends(get_db)):
    if start and end and start > end:
        raise HTTPException(422, "start must not exceed end")
    with database_errors(db):
        rows = [service.present(row) for row in service.observations(
            db, location_id, synthetic=dataset == "synthetic", source=source,
            start=start, end=end, limit=limit, offset=offset)]
        return WeatherHistory(location_id=location_id, source_type=dataset,
                              notice=RESEARCH_NOTICE if dataset == "synthetic" else None,
                              observations=rows, limit=limit, offset=offset)
