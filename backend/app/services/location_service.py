from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.location import Division, Location
from app.models.prediction import Prediction


class LocationNotFoundError(Exception):
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
