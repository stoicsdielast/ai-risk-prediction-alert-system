"""Load the Fiji demo locations and their labelled sample risks.

Safe to run repeatedly: each location is matched by slug, so existing rows are
reset to the demo values and missing rows are added. Locations that are not in
the demo set are left untouched.

Sample risks are stored with source ``SAMPLE`` so they can never be mistaken
for model output. Each run replaces the sample predictions of the demo
locations and leaves any ``MODEL`` predictions alone. Demo locations without a
sample risk are there on purpose, to exercise the "No prediction available"
state.

From the ``backend`` directory:

    python -m app.db.seed_locations
"""

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.init_db import create_tables
from app.db.session import get_session_factory
from app.models.location import Division, Location
from app.models.prediction import PredictionSource, RiskLevel, RiskPrediction


@dataclass(frozen=True)
class SampleRisk:
    risk_level: RiskLevel
    confidence_percent: int
    label: str
    summary: str


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
        SampleRisk(
            RiskLevel.MODERATE, 78, "Elevated urban flood potential",
            "Drainage pressure may increase if rainfall persists for another 2–3 hours.",
        ),
    ),
    DemoLocation(
        "nausori", "Nausori", Division.CENTRAL, -18.0240, 178.5450,
        SampleRisk(
            RiskLevel.HIGH, 84, "High lowland flood potential",
            "Low-lying areas near the Rewa system may experience increased flood impacts.",
        ),
    ),
    DemoLocation("navua", "Navua", Division.CENTRAL, -18.2167, 178.1667),
    DemoLocation(
        "nadi", "Nadi", Division.WESTERN, -17.7765, 177.4356,
        SampleRisk(
            RiskLevel.VERY_HIGH, 92, "Severe river flood potential",
            "Rapid river response is likely in low-lying parts of the Nadi catchment.",
        ),
    ),
    DemoLocation(
        "lautoka", "Lautoka", Division.WESTERN, -17.6169, 177.4505,
        SampleRisk(
            RiskLevel.HIGH, 86, "High surface-water flood potential",
            "Runoff accumulation is expected around poor-drainage and coastal locations.",
        ),
    ),
    DemoLocation(
        "ba", "Ba", Division.WESTERN, -17.5340, 177.6830,
        SampleRisk(
            RiskLevel.HIGH, 88, "High river flood potential",
            "Catchment saturation indicates a heightened chance of river-level rises.",
        ),
    ),
    DemoLocation(
        "sigatoka", "Sigatoka", Division.WESTERN, -18.1410, 177.5070,
        SampleRisk(
            RiskLevel.MODERATE, 71, "Moderate river response possible",
            "Continued rainfall could produce localised rises along smaller tributaries.",
        ),
    ),
    DemoLocation("rakiraki", "Rakiraki", Division.WESTERN, -17.3833, 178.0833),
    DemoLocation(
        "labasa", "Labasa", Division.NORTHERN, -16.4306, 179.3710,
        SampleRisk(
            RiskLevel.LOW, 81, "Low flood potential",
            "Observed rainfall and catchment response remain below concern thresholds.",
        ),
    ),
    DemoLocation(
        "savusavu", "Savusavu", Division.NORTHERN, -16.7799, 179.3330,
        SampleRisk(
            RiskLevel.LOW, 83, "Low flood potential",
            "No significant flood response is expected under current conditions.",
        ),
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
        locations.append((location, demo))

    db.flush()

    db.execute(
        delete(RiskPrediction).where(
            RiskPrediction.location_id.in_([location.id for location, _ in locations]),
            RiskPrediction.source == PredictionSource.SAMPLE,
        )
    )

    sample_risks = 0
    for location, demo in locations:
        if demo.sample_risk is None:
            continue
        db.add(
            RiskPrediction(
                location_id=location.id,
                risk_level=demo.sample_risk.risk_level,
                confidence_percent=demo.sample_risk.confidence_percent,
                label=demo.sample_risk.label,
                summary=demo.sample_risk.summary,
                source=PredictionSource.SAMPLE,
            )
        )
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
