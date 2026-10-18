"""Locations a signed-in user has saved as priority areas to keep an eye on."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.location import Location


class PriorityLocation(Base):
    __tablename__ = "priority_locations"
    __table_args__ = (
        UniqueConstraint("user_id", "location_id", name="uq_priority_location_user_location"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # A saved area is a personal preference, so it goes when the user or
    # location does.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
    )
    location: Mapped[Location] = relationship()
