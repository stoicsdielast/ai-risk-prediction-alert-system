"""MET-admin read-only analytics. No writes, no prediction generation, no model changes."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import require_met_admin
from app.db.session import get_db
from app.models.user import User
from app.services import analytics_service as service

router = APIRouter(prefix="/api/admin/analytics", tags=["admin analytics"])


@router.get("/predictions/overview")
def overview(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db),
             _admin: User = Depends(require_met_admin)):
    return service.prediction_overview(db, days)


@router.get("/predictions/trend")
def trend(location_id: list[int] = Query(default=[], max_length=50), days: int = Query(7, ge=1, le=365),
          source: Literal["operational", "synthetic"] = "operational",
          db: Session = Depends(get_db), _admin: User = Depends(require_met_admin)):
    try:
        ids = service.validate_locations(db, location_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    return service.prediction_trend(db, ids, days, source)


@router.get("/models/performance")
def model_performance(db: Session = Depends(get_db), _admin: User = Depends(require_met_admin)):
    return service.model_performance(db)
