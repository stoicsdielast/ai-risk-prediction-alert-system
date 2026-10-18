from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

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


class LocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    name: str
    division: Division
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
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
            slug=location.slug,
            name=location.name,
            division=location.division,
            latitude=location.latitude,
            longitude=location.longitude,
            prediction=(
                PredictionResponse.model_validate(prediction)
                if prediction is not None
                else None
            ),
        )
