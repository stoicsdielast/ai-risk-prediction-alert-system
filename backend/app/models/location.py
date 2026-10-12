"""Monitored locations: shown on the weather map and referenced by alerts."""

from enum import Enum

from sqlalchemy import Boolean, CheckConstraint, Enum as SqlEnum, Float, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Division(str, Enum):
    CENTRAL = "CENTRAL"
    WESTERN = "WESTERN"
    NORTHERN = "NORTHERN"
    EASTERN = "EASTERN"

    @property
    def label(self) -> str:
        return f"{self.value.title()} Division"


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_location_name"),
        CheckConstraint(
            "latitude >= -90 AND latitude <= 90",
            name="ck_locations_latitude_range",
        ),
        CheckConstraint(
            "longitude >= -180 AND longitude <= 180",
            name="ck_locations_longitude_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stable public identifier used in URLs and by the frontend map.
    slug: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    division: Mapped[Division] = mapped_column(
        SqlEnum(Division, name="division"),
        index=True,
        nullable=False,
    )
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true"),
    )
