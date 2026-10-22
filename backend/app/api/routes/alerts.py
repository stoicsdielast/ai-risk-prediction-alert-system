"""Thin authenticated administrator actions and a separate public alert read API."""

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_met_admin
from app.db.session import get_db
from app.models.alert import AlertStatus
from app.models.user import User
from app.schemas.alert import (
    AlertClosureRequest, AlertDetailResponse, AlertResponse, AlertSuppressionRequest, AlertUpdate, ManualAlertCreate,
)
from app.services import alert_demo_service, alert_service
from app.core.config import get_settings

admin_router = APIRouter(prefix="/api/admin/alerts", tags=["admin alerts"])
public_router = APIRouter(prefix="/api/alerts", tags=["public alerts"])


@admin_router.post("/demo/{scenario}", response_model=AlertDetailResponse)
def create_demo_scenario(
    scenario: str, db: Session = Depends(get_db), _admin: User = Depends(require_met_admin),
) -> AlertDetailResponse:
    if not get_settings().alert_demo_enabled:
        raise HTTPException(status_code=404, detail="Alert demonstrations are disabled")
    return _service_call(lambda: AlertDetailResponse.model_validate(
        alert_demo_service.create_demo_alert(db, scenario),
    ))


def _service_call[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except (
        alert_service.AlertNotFoundError, alert_service.LocationNotFoundError,
        alert_service.PredictionNotFoundError,
    ) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except (alert_service.InvalidAlertStateError, alert_service.AlertConflictError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except (alert_service.InactiveLocationError, alert_service.InvalidAlertDataError) as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except alert_service.AlertServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to process alert request",
        ) from error


@admin_router.post("", response_model=AlertDetailResponse, status_code=status.HTTP_201_CREATED)
def create_manual_alert(
    data: ManualAlertCreate, db: Session = Depends(get_db), admin: User = Depends(require_met_admin),
) -> AlertDetailResponse:
    return _service_call(lambda: AlertDetailResponse.model_validate(
        alert_service.create_manual_alert(db, data, admin),
    ))


@admin_router.post("/from-prediction/{prediction_id}", response_model=AlertDetailResponse | None)
def create_recommendation(
    prediction_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_met_admin),
) -> AlertDetailResponse | None:
    alert = _service_call(lambda: alert_service.create_alert_for_prediction_id(db, prediction_id))
    return AlertDetailResponse.model_validate(alert) if alert is not None else None


@admin_router.get("", response_model=list[AlertDetailResponse])
def list_alerts(
    status_filter: AlertStatus = Query(default=AlertStatus.PENDING, alias="status"),
    offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db), _admin: User = Depends(require_met_admin),
) -> list[AlertDetailResponse]:
    return _service_call(lambda: [
        AlertDetailResponse.model_validate(alert) for alert in alert_service.get_pending_alerts(
            db, status_filter, offset=offset, limit=limit,
        )
    ])


@admin_router.get("/{alert_id}", response_model=AlertDetailResponse)
def get_alert(
    alert_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_met_admin),
) -> AlertDetailResponse:
    return _service_call(lambda: AlertDetailResponse.model_validate(alert_service.get_alert(db, alert_id)))


@admin_router.patch("/{alert_id}", response_model=AlertDetailResponse)
def edit_alert(
    alert_id: int, data: AlertUpdate,
    db: Session = Depends(get_db), admin: User = Depends(require_met_admin),
) -> AlertDetailResponse:
    return _service_call(lambda: AlertDetailResponse.model_validate(
        alert_service.update_alert(db, alert_id, data, admin),
    ))


@admin_router.patch("/{alert_id}/approve", response_model=AlertDetailResponse)
def approve_alert(
    alert_id: int, db: Session = Depends(get_db), admin: User = Depends(require_met_admin),
) -> AlertDetailResponse:
    return _service_call(lambda: AlertDetailResponse.model_validate(
        alert_service.approve_alert(db, alert_id, admin),
    ))


@admin_router.patch("/{alert_id}/reject", response_model=AlertDetailResponse)
def reject_alert(
    alert_id: int, db: Session = Depends(get_db), admin: User = Depends(require_met_admin),
) -> AlertDetailResponse:
    return _service_call(lambda: AlertDetailResponse.model_validate(
        alert_service.reject_alert(db, alert_id, admin),
    ))


@admin_router.patch("/{alert_id}/suppress", response_model=AlertDetailResponse)
def suppress_alert(
    alert_id: int, data: AlertSuppressionRequest,
    db: Session = Depends(get_db), admin: User = Depends(require_met_admin),
) -> AlertDetailResponse:
    return _service_call(lambda: AlertDetailResponse.model_validate(
        alert_service.suppress_alert(db, alert_id, data, admin),
    ))


@public_router.get("/active", response_model=list[AlertResponse])
def public_active_alerts(
    offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[AlertResponse]:
    return _service_call(lambda: [
        AlertResponse.model_validate(alert) for alert in alert_service.get_public_alerts(
            db, offset=offset, limit=limit,
        )
    ])


@admin_router.patch("/{alert_id}/acknowledge", response_model=AlertDetailResponse)
def acknowledge_alert(alert_id: int, db: Session = Depends(get_db), admin: User = Depends(require_met_admin)):
    return _service_call(lambda: AlertDetailResponse.model_validate(alert_service.acknowledge_alert(db, alert_id, admin)))


@admin_router.patch("/{alert_id}/resolve", response_model=AlertDetailResponse)
def resolve_alert(alert_id: int, data: AlertClosureRequest, db: Session = Depends(get_db), admin: User = Depends(require_met_admin)):
    return _service_call(lambda: AlertDetailResponse.model_validate(
        alert_service.close_alert(db, alert_id, data, admin, target=AlertStatus.RESOLVED)))


@admin_router.patch("/{alert_id}/cancel", response_model=AlertDetailResponse)
def cancel_alert(alert_id: int, data: AlertClosureRequest, db: Session = Depends(get_db), admin: User = Depends(require_met_admin)):
    return _service_call(lambda: AlertDetailResponse.model_validate(
        alert_service.close_alert(db, alert_id, data, admin, target=AlertStatus.CANCELLED)))
