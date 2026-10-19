from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

MEASUREMENTS = (
    "rainfall_mm", "temperature_c", "humidity_pct", "pressure_hpa", "wind_speed_mps",
    "wind_direction_deg", "river_level_m", "river_discharge_m3s", "soil_moisture_pct",
    "upstream_rainfall_mm", "coastal_tide_m",
)
RESEARCH_NOTICE = "Synthetic research demonstration only; not Fiji MET readings or a real forecast."


class WeatherCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)
    location_id: int = Field(gt=0)
    observed_at: AwareDatetime
    source: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    source_type: Literal["manual", "provider", "synthetic"] = "manual"
    rainfall_mm: float | None = Field(default=None, ge=0, le=5000)
    rainfall_period_minutes: int | None = Field(default=None, ge=1, le=10080)
    temperature_c: float | None = Field(default=None, ge=-90, le=60)
    humidity_pct: float | None = Field(default=None, ge=0, le=100)
    pressure_hpa: float | None = Field(default=None, ge=800, le=1100)
    wind_speed_mps: float | None = Field(default=None, ge=0, le=150)
    wind_direction_deg: float | None = Field(default=None, ge=0, lt=360)
    river_level_m: float | None = Field(default=None, ge=-100, le=1000)
    river_discharge_m3s: float | None = Field(default=None, ge=0, le=1000000)
    soil_moisture_pct: float | None = Field(default=None, ge=0, le=100)
    upstream_rainfall_mm: float | None = Field(default=None, ge=0, le=5000)
    upstream_rainfall_period_minutes: int | None = Field(default=None, ge=1, le=10080)
    coastal_tide_m: float | None = Field(default=None, ge=-20, le=20)
    gauge_datum: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("observed_at")
    @classmethod
    def timestamp(cls, value):
        value = value.astimezone(timezone.utc)
        if value > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("Observation cannot be more than five minutes in the future")
        return value

    @model_validator(mode="after")
    def measurements(self):
        if not any(getattr(self, name) is not None for name in MEASUREMENTS):
            raise ValueError("At least one measurement is required; missing values must be null")
        if (self.rainfall_mm is None) != (self.rainfall_period_minutes is None):
            raise ValueError("Rainfall amount and accumulation period must be supplied together")
        if (self.upstream_rainfall_mm is None) != (self.upstream_rainfall_period_minutes is None):
            raise ValueError("Upstream rainfall amount and accumulation period must be supplied together")
        return self


class WeatherResponse(BaseModel):
    id: int
    location_id: int
    observed_at: datetime
    received_at: datetime
    source: str
    source_type: Literal["manual", "provider", "synthetic"]
    rainfall_mm: float | None
    rainfall_period_minutes: int | None
    temperature_c: float | None
    humidity_pct: float | None
    pressure_hpa: float | None
    wind_speed_mps: float | None
    wind_direction_deg: float | None
    river_level_m: float | None
    river_discharge_m3s: float | None
    soil_moisture_pct: float | None
    upstream_rainfall_mm: float | None
    upstream_rainfall_period_minutes: int | None
    coastal_tide_m: float | None
    gauge_datum: str | None
    missing_fields: list[str]
    stale: bool
    age_seconds: float
    notice: str | None


class LatestWeather(BaseModel):
    location_id: int
    status: Literal["no_data", "fresh", "stale"]
    source_type: str
    notice: str | None
    observation: WeatherResponse | None


class WeatherHistory(BaseModel):
    location_id: int
    source_type: str
    notice: str | None
    observations: list[WeatherResponse]
    limit: int
    offset: int
