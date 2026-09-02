from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.user import AccountStatus, User


class UserNotFoundError(Exception):
    pass


class InvalidAccountTransitionError(Exception):
    def __init__(self, current_status: AccountStatus):
        self.current_status = current_status
        super().__init__(current_status.value)


class AdminServiceError(Exception):
    pass


def list_pending_users(db: Session) -> list[User]:
    try:
        return list(
            db.scalars(
                select(User)
                .where(User.status == AccountStatus.PENDING)
                .order_by(User.id)
            )
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise AdminServiceError from exc


def transition_user_status(
    db: Session,
    user_id: int,
    target_status: AccountStatus,
) -> User:
    try:
        user = db.scalar(
            select(User).where(User.id == user_id).with_for_update()
        )
        if user is None:
            raise UserNotFoundError
        if user.status != AccountStatus.PENDING:
            raise InvalidAccountTransitionError(user.status)

        user.status = target_status
        db.commit()
        return user
    except (UserNotFoundError, InvalidAccountTransitionError):
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise AdminServiceError from exc
