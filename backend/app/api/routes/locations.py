from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_met_admin
from app.db.session import get_db
from app.models.location import Division
from app.models.user import User
from app.schemas.location import (
    DivisionResponse,
    LocationCreate,
    LocationResponse,
    LocationUpdate,
)
from app.services.location_service import (
    LocationConflictError,
    LocationNotFoundError,
    LocationServiceError,
    create_location,
    get_location_by_id,
    get_location_by_slug,
    latest_predictions,
    list_locations,
    update_location,
)


# Read-only and public: the weather map is available to visitors who are not
# signed in.
router = APIRouter(prefix="/api/locations", tags=["locations"])

# Administrator location management (create/update/deactivate). No hard delete:
# predictions and alerts reference locations with RESTRICT foreign keys, so
# deactivation (is_active=false) is the supported way to retire a location.
admin_router = APIRouter(prefix="/api/admin/locations", tags=["admin locations"])


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
        locations = list_locations(db, division=division, search=search)
        predictions = latest_predictions(db, [location.id for location in locations])
    except LocationServiceError as exc:
        raise _service_unavailable() from exc

    return [
        LocationResponse.from_location(location, predictions.get(location.id))
        for location in locations
    ]


@router.get("/divisions", response_model=list[DivisionResponse])
def get_divisions() -> list[DivisionResponse]:
    return [
        DivisionResponse(code=division, label=division.label)
        for division in Division
    ]


@router.get("/{slug}", response_model=LocationResponse)
def get_location(slug: str, db: Session = Depends(get_db)) -> LocationResponse:
    try:
        location = get_location_by_slug(db, slug)
        prediction = latest_predictions(db, [location.id]).get(location.id)
    except LocationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found",
        ) from exc
    except LocationServiceError as exc:
        raise _service_unavailable() from exc

    return LocationResponse.from_location(location, prediction)


@admin_router.post("", response_model=LocationResponse, status_code=status.HTTP_201_CREATED)
def create_location_route(
    data: LocationCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_met_admin),
) -> LocationResponse:
    try:
        location = create_location(db, data)
        prediction = latest_predictions(db, [location.id]).get(location.id)
    except LocationConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except LocationServiceError as exc:
        raise _service_unavailable() from exc

    return LocationResponse.from_location(location, prediction)


@admin_router.patch("/{location_id}", response_model=LocationResponse)
def update_location_route(
    location_id: int,
    data: LocationUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_met_admin),
) -> LocationResponse:
    try:
        location = update_location(db, location_id, data)
        prediction = latest_predictions(db, [location.id]).get(location.id)
    except LocationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found",
        ) from exc
    except LocationConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except LocationServiceError as exc:
        raise _service_unavailable() from exc

    return LocationResponse.from_location(location, prediction)
