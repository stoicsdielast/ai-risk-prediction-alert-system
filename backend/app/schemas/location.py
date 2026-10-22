from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.models.location import Division, Location
from app.models.prediction import Prediction
from app.models.risk import RiskLevel


class DivisionResponse(BaseModel):
    code: Division
    label: str


class PredictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    risk_level: RiskLevel
    # P(flood) from the model, 0–1. Not a calibrated confidence score.
    flood_probability: float = Field(ge=0, le=1)
    model_version: str
    is_sample: bool
    predicted_at: datetime


class LocationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # Whitespace-only names are rejected: stripping runs before min_length.
    name: str = Field(min_length=1, max_length=255)
    # Stable public identifier; immutable after creation.
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    division: Division
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class LocationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=255)
    division: Division | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_provided_fields(self) -> "LocationUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        null_fields = sorted(
            name for name in self.model_fields_set if getattr(self, name) is None
        )
        if null_fields:
            raise ValueError(f"Fields cannot be null: {', '.join(null_fields)}")
        return self


class LocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    division: Division
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    # Public reads only ever return active locations; the field exists so
    # administrator responses can confirm (de)activation.
    is_active: bool = True
    # None means no prediction is available for this location.
    prediction: PredictionResponse | None = None

    @computed_field
    @property
    def division_label(self) -> str:
        return self.division.label

    @classmethod
    def from_location(
        cls,
        location: Location,
        prediction: Prediction | None,
    ) -> "LocationResponse":
        return cls(
            id=location.id,
            slug=location.slug,
            name=location.name,
            division=location.division,
            latitude=location.latitude,
            longitude=location.longitude,
            is_active=location.is_active,
            prediction=(
                PredictionResponse.model_validate(prediction)
                if prediction is not None
                else None
            ),
        )
