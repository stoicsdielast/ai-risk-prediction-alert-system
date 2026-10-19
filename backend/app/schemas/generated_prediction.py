from datetime import datetime, timezone
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

NOTICE = "Synthetic V1 research demonstration; not an official Fiji MET forecast or emergency warning."


class GeneratePrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location_id: int = Field(gt=0)
    timestamp: AwareDatetime
    source: str = Field(min_length=1, max_length=100)
    source_type: Literal["synthetic", "manual", "provider"]
    research_mode: bool
    historical_replay: bool = False

    @field_validator("timestamp")
    @classmethod
    def exact_hour(cls, value):
        value = value.astimezone(timezone.utc)
        if value.minute or value.second or value.microsecond:
            raise ValueError("V1 requires an exact UTC hourly timestamp")
        if value > datetime.now(timezone.utc):
            raise ValueError("Prediction timestamp cannot be in the future")
        return value


class GeneratedPredictionResponse(BaseModel):
    status: Literal["OK", "DATA_UNAVAILABLE"]
    reason: str | None = None
    location_id: int
    timestamp: datetime
    source: str
    source_type: str
    research_mode: bool = True
    historical_replay: bool
    notice: str = NOTICE
    prediction_id: int | None = None
    probability: float | None = None
    risk_category: str | None = None
    horizon_hours: int = 24
    model_version: str | None = None
    generated_at: datetime | None = None
    alert_id: int | None = None
    alert_status: str | None = None
    input_sha256: str | None = None
    current_flood_state_assessed: bool = False
