from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictFloat, StrictInt, field_validator, model_validator


class ResearchPredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    mode: Literal["historical_replay"]
    country: Literal["Bangladesh"]
    station_id: str = Field(min_length=1, max_length=32, pattern=r"^[A-Z0-9_]+$")
    feature_date: date
    as_of: AwareDatetime
    # Missing measurements return data_unavailable. Strings and booleans are
    # rejected, rather than silently cast into hydrological measurements.
    features: dict[str, StrictFloat | StrictInt | None] = Field(default_factory=dict, max_length=64)

    @field_validator("feature_date")
    @classmethod
    def historical_date(cls, value):
        if value < date(1950, 1, 1) or value > datetime.now(timezone.utc).date():
            raise ValueError("feature_date must be historical and within the source era")
        return value

    @model_validator(mode="after")
    def closed_daily_window(self):
        day_end = datetime.combine(self.feature_date, time(23, 59, 59), tzinfo=timezone.utc)
        stamp = self.as_of.astimezone(timezone.utc)
        if not day_end <= stamp < day_end + timedelta(days=1):
            raise ValueError("as_of must follow the closed feature day, within 24 hours (UTC replay convention)")
        if stamp > datetime.now(timezone.utc):
            raise ValueError("as_of must not be in the future")
        return self


class ResearchPredictionResponse(BaseModel):
    status: Literal["ok", "data_unavailable"]
    research_mode: Literal[True] = True
    mode: Literal["historical_replay"] = "historical_replay"
    country: Literal["Bangladesh"] = "Bangladesh"
    probability: float | None = Field(default=None, ge=0, le=1)
    presentation_tier: Literal["LOW", "MODERATE", "HIGH", "VERY_HIGH"] | None = None
    prediction_horizon_hours: Literal[24] = 24
    model_version: str | None = None
    timestamp: datetime
    generated_at: datetime
    station_id: str
    source: str
    disclaimer: str
    missing_features: list[str] = Field(default_factory=list)
    reason: str | None = None
    binary_threshold: float | None = None
    binary_prediction: int | None = None
    prediction_id: int | None = None
