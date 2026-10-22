"""Idempotent upgrade of the pre-map PostgreSQL schema.

Run through ``python -m app.db.init_db`` (also used by the demo seed command).
The caller owns the transaction, so an unsuccessful upgrade leaves data intact.
Unknown legacy locations require real coordinates before the upgrade can proceed.
"""

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM


# Frozen backfill for the original Fiji demo locations. Do not invent coordinates
# for other legacy rows or depend on future changes to the demo seed data.
LEGACY_LOCATIONS = {
    "suva": ("suva", "CENTRAL", -18.1416, 178.4419),
    "nausori": ("nausori", "CENTRAL", -18.0240, 178.5450),
    "navua": ("navua", "CENTRAL", -18.2167, 178.1667),
    "nadi": ("nadi", "WESTERN", -17.7765, 177.4356),
    "lautoka": ("lautoka", "WESTERN", -17.6169, 177.4505),
    "ba": ("ba", "WESTERN", -17.5340, 177.6830),
    "sigatoka": ("sigatoka", "WESTERN", -18.1410, 177.5070),
    "rakiraki": ("rakiraki", "WESTERN", -17.3833, 178.0833),
    "labasa": ("labasa", "NORTHERN", -16.4306, 179.3710),
    "savusavu": ("savusavu", "NORTHERN", -16.7799, 179.3330),
    "levuka": ("levuka", "EASTERN", -17.6833, 178.8333),
    "vunisea (kadavu)": ("vunisea", "EASTERN", -19.0500, 178.1667),
}
LOCATION_FIELDS = ("slug", "division", "latitude", "longitude")


def upgrade_location_schema(connection: sa.Connection) -> None:
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())
    operations = Operations(MigrationContext.configure(connection))

    if "locations" in tables:
        columns = {column["name"]: column for column in inspector.get_columns("locations")}
        missing = set(LOCATION_FIELDS) - columns.keys()
        nullable = {name for name in LOCATION_FIELDS if name in columns and columns[name]["nullable"]}
        if missing or nullable:
            if connection.dialect.name != "postgresql":
                raise RuntimeError("Upgrading legacy location tables requires PostgreSQL")

            updates = []
            for row in connection.execute(sa.text("SELECT * FROM locations")).mappings():
                values = dict(row)
                demo = LEGACY_LOCATIONS.get(row["name"].strip().casefold())
                for name, value in zip(LOCATION_FIELDS, demo or (None,) * 4):
                    if values.get(name) is None:
                        values[name] = value
                if any(values.get(name) is None for name in LOCATION_FIELDS):
                    raise RuntimeError(
                        f"Location {row['id']} needs a slug, division, latitude and longitude. "
                        "Supply verified location data before rerunning init_db; no rows were deleted."
                    )
                updates.append({"id": row["id"], **{name: values[name] for name in LOCATION_FIELDS}})

            division = ENUM("CENTRAL", "WESTERN", "NORTHERN", "EASTERN", name="division")
            division.create(connection, checkfirst=True)
            types = {"slug": sa.String(64), "division": division, "latitude": sa.Float(), "longitude": sa.Float()}
            for name in LOCATION_FIELDS:
                if name in missing:
                    operations.add_column("locations", sa.Column(name, types[name], nullable=True))
            if updates:
                connection.execute(sa.text(
                    "UPDATE locations SET slug=:slug, division=CAST(:division AS division), "
                    "latitude=:latitude, longitude=:longitude WHERE id=:id"
                ), updates)
            for name in missing | nullable:
                operations.alter_column("locations", name, nullable=False)

        indexes = {index["name"] for index in inspector.get_indexes("locations")}
        if "ix_locations_slug" not in indexes:
            operations.create_index("ix_locations_slug", "locations", ["slug"], unique=True)
        if "ix_locations_division" not in indexes:
            operations.create_index("ix_locations_division", "locations", ["division"])
        checks = {check["name"] for check in inspector.get_check_constraints("locations")}
        for name, expression in (
            ("ck_locations_latitude_range", "latitude >= -90 AND latitude <= 90"),
            ("ck_locations_longitude_range", "longitude >= -180 AND longitude <= 180"),
        ):
            if name not in checks:
                operations.create_check_constraint(name, "locations", expression)

    if "predictions" in tables:
        columns = {column["name"] for column in inspector.get_columns("predictions")}
        if "is_sample" not in columns:
            operations.add_column("predictions", sa.Column(
                "is_sample", sa.Boolean(), nullable=False, server_default=sa.false(),
            ))
