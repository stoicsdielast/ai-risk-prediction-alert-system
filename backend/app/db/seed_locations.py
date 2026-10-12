"""Load the Fiji demo locations.

Safe to run repeatedly: each location is matched by slug, so existing rows are
reset to the demo values and missing rows are added. Locations that are not in
the demo set are left untouched.

From the ``backend`` directory:

    python -m app.db.seed_locations
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.init_db import create_tables
from app.db.session import get_session_factory
from app.models.location import Division, Location


@dataclass(frozen=True)
class DemoLocation:
    slug: str
    name: str
    division: Division
    latitude: float
    longitude: float


# Town-centre coordinates. All sit west of the antimeridian so the map can fit
# them in a single view.
DEMO_LOCATIONS: tuple[DemoLocation, ...] = (
    DemoLocation("suva", "Suva", Division.CENTRAL, -18.1416, 178.4419),
    DemoLocation("nausori", "Nausori", Division.CENTRAL, -18.0240, 178.5450),
    DemoLocation("navua", "Navua", Division.CENTRAL, -18.2167, 178.1667),
    DemoLocation("nadi", "Nadi", Division.WESTERN, -17.7765, 177.4356),
    DemoLocation("lautoka", "Lautoka", Division.WESTERN, -17.6169, 177.4505),
    DemoLocation("ba", "Ba", Division.WESTERN, -17.5340, 177.6830),
    DemoLocation("sigatoka", "Sigatoka", Division.WESTERN, -18.1410, 177.5070),
    DemoLocation("rakiraki", "Rakiraki", Division.WESTERN, -17.3833, 178.0833),
    DemoLocation("labasa", "Labasa", Division.NORTHERN, -16.4306, 179.3710),
    DemoLocation("savusavu", "Savusavu", Division.NORTHERN, -16.7799, 179.3330),
    DemoLocation("levuka", "Levuka", Division.EASTERN, -17.6833, 178.8333),
    DemoLocation("vunisea", "Vunisea (Kadavu)", Division.EASTERN, -19.0500, 178.1667),
)


@dataclass(frozen=True)
class SeedResult:
    created: int
    updated: int


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

    db.commit()
    return SeedResult(created=created, updated=updated)


def main() -> None:
    create_tables()
    with get_session_factory()() as db:
        result = seed_demo_locations(db)
    print(
        f"Demo locations ready: {result.created} created, "
        f"{result.updated} refreshed."
    )


if __name__ == "__main__":
    main()
