"""Minimal monitored-location reference required by the alert workflow."""

from sqlalchemy import Boolean, CheckConstraint, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (CheckConstraint("length(trim(name)) > 0", name="ck_location_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true"),
    )
