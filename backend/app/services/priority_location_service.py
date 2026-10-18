from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.location import Location
from app.models.priority_location import PriorityLocation
from app.models.user import User
from app.services.location_service import (
    LocationNotFoundError,
    LocationServiceError,
    get_location_by_slug,
)


def list_priority_locations(db: Session, user: User) -> list[Location]:
    """Return the user's saved locations that are still monitored, by name."""
    query = (
        select(Location)
        .join(PriorityLocation, PriorityLocation.location_id == Location.id)
        .where(
            PriorityLocation.user_id == user.id,
            Location.is_active.is_(True),
        )
        .order_by(Location.name, Location.id)
    )
    try:
        return list(db.scalars(query))
    except SQLAlchemyError as exc:
        db.rollback()
        raise LocationServiceError from exc


def add_priority_location(db: Session, user: User, slug: str) -> Location:
    """Save an active location as a priority area. Saving it again is a no-op."""
    location = get_location_by_slug(db, slug)

    try:
        already_saved = db.scalar(
            select(PriorityLocation.id).where(
                PriorityLocation.user_id == user.id,
                PriorityLocation.location_id == location.id,
            )
        )
        if already_saved is None:
            db.add(PriorityLocation(user_id=user.id, location_id=location.id))
            db.commit()
    except IntegrityError:
        # A concurrent request saved the same location first.
        db.rollback()
    except SQLAlchemyError as exc:
        db.rollback()
        raise LocationServiceError from exc

    return location


def remove_priority_location(db: Session, user: User, slug: str) -> None:
    """Remove a saved location. Removing one that was not saved is a no-op.

    Inactive locations can still be removed, so a user can tidy up an area
    that is no longer monitored.
    """
    try:
        location_id = db.scalar(select(Location.id).where(Location.slug == slug))
        if location_id is None:
            raise LocationNotFoundError
        db.execute(
            delete(PriorityLocation).where(
                PriorityLocation.user_id == user.id,
                PriorityLocation.location_id == location_id,
            )
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise LocationServiceError from exc
