"""Load the Fiji demo locations and their labelled sample risks.

Safe to run repeatedly: each location is matched by slug, so existing rows are
reset to the demo values and missing rows are added. Locations that are not in
the demo set are left untouched.

Sample risks are stored as predictions with ``is_sample = true`` so they can
never be mistaken for model output. Each run resets the sample prediction of
every demo location in place (alerts may reference it, so it is not deleted)
and leaves real predictions alone. Demo locations without a sample risk are
there on purpose, to exercise the "No prediction available" state.

Sample probabilities agree with the development thresholds in ``ai/config.py``.

From the ``backend`` directory:

    python -m app.db.seed_locations
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.init_db import create_tables
from app.db.session import get_session_factory
from app.models.location import Division, Location
from app.models.prediction import ALERT_DEMO_MODEL_PREFIX, Prediction
from app.models.risk import RiskLevel


SAMPLE_MODEL_VERSION = "sample-demo-not-a-model-result"


@dataclass(frozen=True)
class SampleRisk:
    risk_level: RiskLevel
    flood_probability: float


@dataclass(frozen=True)
class DemoLocation:
    slug: str
    name: str
    division: Division
    latitude: float
    longitude: float
    sample_risk: SampleRisk | None = None


# Town-centre coordinates. All sit west of the antimeridian so the map can fit
# them in a single view.
DEMO_LOCATIONS: tuple[DemoLocation, ...] = (
    DemoLocation(
        "suva", "Suva", Division.CENTRAL, -18.1416, 178.4419,
        SampleRisk(RiskLevel.MODERATE, 0.38),
    ),
    DemoLocation(
        "nausori", "Nausori", Division.CENTRAL, -18.0240, 178.5450,
        SampleRisk(RiskLevel.HIGH, 0.74),
    ),
    DemoLocation("navua", "Navua", Division.CENTRAL, -18.2167, 178.1667),
    DemoLocation(
        "nadi", "Nadi", Division.WESTERN, -17.7765, 177.4356,
        SampleRisk(RiskLevel.VERY_HIGH, 0.91),
    ),
    DemoLocation(
        "lautoka", "Lautoka", Division.WESTERN, -17.6169, 177.4505,
        SampleRisk(RiskLevel.HIGH, 0.63),
    ),
    DemoLocation(
        "ba", "Ba", Division.WESTERN, -17.5340, 177.6830,
        SampleRisk(RiskLevel.HIGH, 0.68),
    ),
    DemoLocation(
        "sigatoka", "Sigatoka", Division.WESTERN, -18.1410, 177.5070,
        SampleRisk(RiskLevel.MODERATE, 0.46),
    ),
    DemoLocation("rakiraki", "Rakiraki", Division.WESTERN, -17.3833, 178.0833),
    DemoLocation(
        "labasa", "Labasa", Division.NORTHERN, -16.4306, 179.3710,
        SampleRisk(RiskLevel.LOW, 0.14),
    ),
    DemoLocation(
        "savusavu", "Savusavu", Division.NORTHERN, -16.7799, 179.3330,
        SampleRisk(RiskLevel.LOW, 0.09),
    ),
    DemoLocation("levuka", "Levuka", Division.EASTERN, -17.6833, 178.8333),
    DemoLocation("vunisea", "Vunisea (Kadavu)", Division.EASTERN, -19.0500, 178.1667),
)


@dataclass(frozen=True)
class SeedResult:
    created: int
    updated: int
    sample_risks: int


def seed_demo_locations(db: Session) -> SeedResult:
    existing = {
        location.slug: location
        for location in db.scalars(
            select(Location).where(
                Location.slug.in_([demo.slug for demo in DEMO_LOCATIONS])
            )
        )
    }

    created = updated = 0
    locations: list[tuple[Location, DemoLocation]] = []
    for demo in DEMO_LOCATIONS:
        location = existing.get(demo.slug)
        if location is None:
            location = Location(slug=demo.slug)
            db.add(location)
            created += 1
        else:
            updated += 1

        location.name = demo.name
        location.division = demo.division
        location.latitude = demo.latitude
        location.longitude = demo.longitude
        location.is_active = True
        locations.append((location, demo))

    db.flush()

    existing_samples: dict[int, Prediction] = {}
    for prediction in db.scalars(
        select(Prediction)
        .where(
            Prediction.location_id.in_([location.id for location, _ in locations]),
            Prediction.is_sample.is_(True),
            ~Prediction.model_version.startswith(ALERT_DEMO_MODEL_PREFIX),
        )
        .order_by(Prediction.predicted_at, Prediction.id)
    ):
        existing_samples[prediction.location_id] = prediction

    now = datetime.now(timezone.utc)
    sample_risks = 0
    for location, demo in locations:
        if demo.sample_risk is None:
            continue
        sample = existing_samples.get(location.id)
        if sample is None:
            sample = Prediction(location_id=location.id, is_sample=True)
            db.add(sample)
        sample.risk_level = demo.sample_risk.risk_level
        sample.flood_probability = demo.sample_risk.flood_probability
        sample.model_version = SAMPLE_MODEL_VERSION
        sample.predicted_at = now
        sample_risks += 1

    db.commit()
    return SeedResult(created=created, updated=updated, sample_risks=sample_risks)


def main() -> None:
    create_tables()
    with get_session_factory()() as db:
        result = seed_demo_locations(db)
    print(
        f"Demo locations ready: {result.created} created, "
        f"{result.updated} refreshed, {result.sample_risks} sample risks loaded."
    )


if __name__ == "__main__":
    main()
