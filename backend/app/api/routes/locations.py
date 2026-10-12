from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.location import Division
from app.schemas.location import DivisionResponse, LocationResponse
from app.services.location_service import (
    LocationNotFoundError,
    LocationServiceError,
    get_location_by_slug,
    list_locations,
)


# Read-only and public: the weather map is available to visitors who are not
# signed in.
router = APIRouter(prefix="/api/locations", tags=["locations"])


def _service_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to retrieve locations",
    )


@router.get("", response_model=list[LocationResponse])
def get_locations(
    division: Division | None = None,
    search: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
) -> list[LocationResponse]:
    try:
        return [
            LocationResponse.model_validate(location)
            for location in list_locations(db, division=division, search=search)
        ]
    except LocationServiceError as exc:
        raise _service_unavailable() from exc


@router.get("/divisions", response_model=list[DivisionResponse])
def get_divisions() -> list[DivisionResponse]:
    return [
        DivisionResponse(code=division, label=division.label)
        for division in Division
    ]


@router.get("/{slug}", response_model=LocationResponse)
def get_location(slug: str, db: Session = Depends(get_db)) -> LocationResponse:
    try:
        return LocationResponse.model_validate(get_location_by_slug(db, slug))
    except LocationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found",
        ) from exc
    except LocationServiceError as exc:
        raise _service_unavailable() from exc
