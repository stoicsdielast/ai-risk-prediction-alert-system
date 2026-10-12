from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models.location import Division, Location
from app.models.prediction import PredictionSource, RiskLevel, RiskPrediction


class DivisionResponse(BaseModel):
    code: Division
    label: str


class PredictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    risk_level: RiskLevel
    confidence_percent: int = Field(ge=0, le=100)
    label: str
    summary: str
    source: PredictionSource
    generated_at: datetime

    @computed_field
    @property
    def is_sample(self) -> bool:
        return self.source == PredictionSource.SAMPLE


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
        prediction: RiskPrediction | None,
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
