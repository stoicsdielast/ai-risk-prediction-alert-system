from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.location import LocationResponse
from app.services.location_service import (
    LocationNotFoundError,
    LocationServiceError,
    latest_predictions,
)
from app.services.priority_location_service import (
    add_priority_location,
    list_priority_locations,
    remove_priority_location,
)


# Any approved, active account can keep its own list of priority areas.
router = APIRouter(prefix="/api/me/priority-locations", tags=["priority locations"])


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Location not found",
    )


def _service_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to update priority locations",
    )


@router.get("", response_model=list[LocationResponse])
def get_priority_locations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[LocationResponse]:
    try:
        locations = list_priority_locations(db, current_user)
        predictions = latest_predictions(db, [location.id for location in locations])
    except LocationServiceError as exc:
        raise _service_unavailable() from exc

    return [
        LocationResponse.from_location(location, predictions.get(location.id))
        for location in locations
    ]


@router.put("/{slug}", response_model=LocationResponse)
def save_priority_location(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LocationResponse:
    try:
        location = add_priority_location(db, current_user, slug)
        prediction = latest_predictions(db, [location.id]).get(location.id)
    except LocationNotFoundError as exc:
        raise _not_found() from exc
    except LocationServiceError as exc:
        raise _service_unavailable() from exc

    return LocationResponse.from_location(location, prediction)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
def delete_priority_location(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    try:
        remove_priority_location(db, current_user, slug)
    except LocationNotFoundError as exc:
        raise _not_found() from exc
    except LocationServiceError as exc:
        raise _service_unavailable() from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
