"""Personal subscriptions and an operational-alert-only durable browser outbox."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def now():
    return datetime.now(timezone.utc)


class SavedLocation(Base):
    __tablename__ = "saved_locations"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    browser_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (
        UniqueConstraint("user_id", "alert_id", name="uq_notification_user_alert"),
        CheckConstraint("status IN ('PENDING','DELIVERED','FAILED','CANCELLED')", name="ck_notification_status"),
        CheckConstraint("attempts >= 0", name="ck_notification_attempts"),
        Index("ix_notification_user_status", "user_id", "status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(String(500))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_token: Mapped[str | None] = mapped_column(String(36))
    claimed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationAttempt(Base):
    __tablename__ = "notification_attempts"
    token: Mapped[str] = mapped_column(String(36), primary_key=True)
    notification_id: Mapped[int] = mapped_column(ForeignKey("notification_outbox.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str] = mapped_column(String(16), default="PENDING")
    error: Mapped[str | None] = mapped_column(String(500))
