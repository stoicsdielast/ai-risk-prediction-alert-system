from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.location import Division, Location
from app.models.prediction import Prediction
from app.schemas.location import LocationCreate, LocationUpdate


class LocationNotFoundError(Exception):
    pass


class LocationConflictError(Exception):
    pass


class LocationServiceError(Exception):
    pass


def list_locations(
    db: Session,
    *,
    division: Division | None = None,
    search: str | None = None,
) -> list[Location]:
    query = (
        select(Location)
        .where(Location.is_active.is_(True))
        .order_by(Location.name, Location.id)
    )

    if division is not None:
        query = query.where(Location.division == division)

    normalized_search = (search or "").strip().lower()
    if normalized_search:
        query = query.where(
            func.lower(Location.name).contains(normalized_search, autoescape=True)
        )

    try:
        return list(db.scalars(query))
    except SQLAlchemyError as exc:
        db.rollback()
        raise LocationServiceError from exc


def get_location_by_slug(db: Session, slug: str) -> Location:
    try:
        location = db.scalar(
            select(Location).where(
                Location.slug == slug,
                Location.is_active.is_(True),
            )
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise LocationServiceError from exc

    if location is None:
        raise LocationNotFoundError
    return location


def get_location_by_id(db: Session, location_id: int) -> Location:
    """Admin read: includes inactive locations so they can be reactivated."""
    location = db.get(Location, location_id)
    if location is None:
        raise LocationNotFoundError
    return location


def create_location(db: Session, data: LocationCreate) -> Location:
    """Administrator create. New locations are active immediately."""
    location = Location(**data.model_dump(), is_active=True)
    db.add(location)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise LocationConflictError(
            "A location with this slug already exists"
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise LocationServiceError from exc
    db.commit()
    return location


def update_location(db: Session, location_id: int, data: LocationUpdate) -> Location:
    """Administrator update; slug is immutable. Deactivation keeps the row so
    prediction/alert history stays intact."""
    location = get_location_by_id(db, location_id)

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(location, field, value)

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise LocationConflictError("Location update conflicts with existing data") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise LocationServiceError from exc
    db.commit()
    return location


def latest_predictions(
    db: Session,
    location_ids: list[int],
) -> dict[int, Prediction]:
    """Return the prediction to show for each location that has one.

    A real prediction always takes priority over a sample one; within each
    kind, the most recent wins.
    """
    if not location_ids:
        return {}

    query = (
        select(Prediction)
        .where(Prediction.location_id.in_(location_ids))
        .order_by(Prediction.is_sample.desc(), Prediction.predicted_at, Prediction.id)
    )
    try:
        # Later rows overwrite earlier ones: samples sort first, so a real
        # prediction replaces them, and the latest of each kind is kept.
        return {
            prediction.location_id: prediction
            for prediction in db.scalars(query)
        }
    except SQLAlchemyError as exc:
        db.rollback()
        raise LocationServiceError from exc
