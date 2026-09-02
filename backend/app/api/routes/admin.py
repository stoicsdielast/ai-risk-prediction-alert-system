from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_met_admin
from app.db.session import get_db
from app.models.user import AccountStatus, User
from app.schemas.user import UserResponse
from app.services.admin_service import (
    AdminServiceError,
    InvalidAccountTransitionError,
    UserNotFoundError,
    list_pending_users,
    transition_user_status,
)


router = APIRouter(prefix="/api/admin", tags=["admin"])


def _transition_error_detail(exc: InvalidAccountTransitionError) -> str:
    if exc.current_status == AccountStatus.APPROVED:
        return "Account is already approved"
    return "Account has already been rejected"


def _change_status(
    user_id: int,
    target_status: AccountStatus,
    db: Session,
) -> UserResponse:
    try:
        return UserResponse.model_validate(
            transition_user_status(db, user_id, target_status)
        )
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        ) from exc
    except InvalidAccountTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_transition_error_detail(exc),
        ) from exc
    except AdminServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to update account",
        ) from exc


@router.get("/users/pending", response_model=list[UserResponse])
def get_pending_users(
    db: Session = Depends(get_db),
    _current_admin: User = Depends(require_met_admin),
) -> list[UserResponse]:
    try:
        return [
            UserResponse.model_validate(user)
            for user in list_pending_users(db)
        ]
    except AdminServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve accounts",
        ) from exc


@router.patch("/users/{user_id}/approve", response_model=UserResponse)
def approve_user(
    user_id: int,
    db: Session = Depends(get_db),
    _current_admin: User = Depends(require_met_admin),
) -> UserResponse:
    return _change_status(user_id, AccountStatus.APPROVED, db)


@router.patch("/users/{user_id}/reject", response_model=UserResponse)
def reject_user(
    user_id: int,
    db: Session = Depends(get_db),
    _current_admin: User = Depends(require_met_admin),
) -> UserResponse:
    return _change_status(user_id, AccountStatus.REJECTED, db)
