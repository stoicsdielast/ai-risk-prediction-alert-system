from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import InvalidAccessTokenError, decode_access_token
from app.db.session import get_db
from app.models.user import User, UserRole
from app.services.auth_service import (
    AccountApprovalPendingError,
    AccountRejectedError,
    InactiveAccountError,
    ensure_account_can_authenticate,
)


bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _raise_account_access_error(exc: Exception) -> None:
    if isinstance(exc, InactiveAccountError):
        detail = "Account is inactive"
    elif isinstance(exc, AccountApprovalPendingError):
        detail = "Account approval pending"
    else:
        detail = "Account has been rejected"
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=detail,
    ) from exc


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    try:
        subject = decode_access_token(credentials.credentials)
        user_id = int(subject)
        if user_id <= 0 or str(user_id) != subject:
            raise ValueError
    except (InvalidAccessTokenError, ValueError) as exc:
        raise _unauthorized() from exc

    try:
        user = db.get(User, user_id)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to authenticate request",
        ) from exc

    if user is None:
        raise _unauthorized()

    try:
        ensure_account_can_authenticate(user)
    except (
        AccountApprovalPendingError,
        AccountRejectedError,
        InactiveAccountError,
    ) as exc:
        _raise_account_access_error(exc)

    return user


def require_met_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.MET_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return current_user
