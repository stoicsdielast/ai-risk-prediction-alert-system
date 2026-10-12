from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models.location import Division


class DivisionResponse(BaseModel):
    code: Division
    label: str


class LocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    name: str
    division: Division
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    @computed_field
    @property
    def division_label(self) -> str:
        return self.division.label
