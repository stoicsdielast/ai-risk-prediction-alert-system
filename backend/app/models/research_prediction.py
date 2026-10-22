"""Historical Bangladesh runs have no relationship to Fiji alerts/locations."""
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ResearchPrediction(Base):
    __tablename__ = "research_predictions"
    __table_args__ = (CheckConstraint("country = 'Bangladesh'", name="ck_research_country"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    country: Mapped[str] = mapped_column(String(32), nullable=False, default="Bangladesh")
    station_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    model_version: Mapped[str] = mapped_column(String(255), nullable=False)
    inputs: Mapped[dict] = mapped_column(JSON, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
