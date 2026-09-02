from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.user import AccountStatus, User
from app.schemas.auth import LoginRequest
from app.schemas.user import UserCreate


DUMMY_PASSWORD_HASH = hash_password("authentication-timing-placeholder")


class AccountAlreadyExistsError(Exception):
    pass


class RegistrationError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class AccountApprovalPendingError(Exception):
    pass


class AccountRejectedError(Exception):
    pass


class InactiveAccountError(Exception):
    pass


class AuthenticationServiceError(Exception):
    pass


def _is_duplicate_email_error(exc: IntegrityError) -> bool:
    diagnostic = getattr(exc.orig, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    if constraint_name in {"ix_users_email", "users_email_key"}:
        return True
    return "users.email" in str(exc.orig).lower()


def ensure_account_can_authenticate(user: User) -> None:
    if not user.is_active:
        raise InactiveAccountError
    if user.status == AccountStatus.PENDING:
        raise AccountApprovalPendingError
    if user.status == AccountStatus.REJECTED:
        raise AccountRejectedError
    if user.status != AccountStatus.APPROVED:
        raise AccountRejectedError


def authenticate_user(db: Session, login_data: LoginRequest) -> User:
    try:
        user = db.scalar(select(User).where(User.email == str(login_data.email)))
    except SQLAlchemyError as exc:
        db.rollback()
        raise AuthenticationServiceError from exc

    try:
        password_is_valid = verify_password(
            login_data.password.get_secret_value(),
            user.hashed_password if user is not None else DUMMY_PASSWORD_HASH,
        )
    except Exception as exc:
        raise InvalidCredentialsError from exc

    if user is None or not password_is_valid:
        raise InvalidCredentialsError

    ensure_account_can_authenticate(user)
    return user


def register_user(db: Session, user_data: UserCreate) -> User:
    try:
        existing_user = db.scalar(
            select(User).where(User.email == str(user_data.email))
        )
        if existing_user is not None:
            raise AccountAlreadyExistsError

        user = User(
            name=user_data.name,
            email=str(user_data.email),
            hashed_password=hash_password(user_data.password.get_secret_value()),
            role=user_data.role,
            status=AccountStatus.PENDING,
            is_active=True,
        )
        db.add(user)
        db.commit()
        return user
    except AccountAlreadyExistsError:
        raise
    except IntegrityError as exc:
        db.rollback()
        if _is_duplicate_email_error(exc):
            raise AccountAlreadyExistsError from exc
        raise RegistrationError from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise RegistrationError from exc
