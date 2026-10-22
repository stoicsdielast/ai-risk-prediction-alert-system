"""PostgreSQL migration coverage in a temporary schema, rolled back after each test.

Set TEST_DATABASE_URL to a local PostgreSQL database to run these tests. Existing
tables are never changed: even schema creation is inside the rolled-back transaction.
"""

import os
from uuid import uuid4

import pytest
import sqlalchemy as sa

from app.db.base import Base
from app.db.migrate_locations import upgrade_location_schema


@pytest.fixture
def pg_connection():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL migration tests")
    engine = sa.create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        schema = f"test_location_migration_{uuid4().hex}"
        try:
            connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            yield connection
        finally:
            transaction.rollback()
    engine.dispose()


@pytest.fixture
def legacy(pg_connection):
    Base.metadata.create_all(pg_connection)
    pg_connection.execute(sa.text(
        "ALTER TABLE locations DROP COLUMN slug, DROP COLUMN division, "
        "DROP COLUMN latitude, DROP COLUMN longitude"
    ))
    pg_connection.execute(sa.text("ALTER TABLE predictions DROP COLUMN is_sample"))
    pg_connection.execute(sa.text("DROP TYPE division"))
    return pg_connection


def test_fresh_database_and_repeated_initialization(pg_connection):
    upgrade_location_schema(pg_connection)
    Base.metadata.create_all(pg_connection)
    upgrade_location_schema(pg_connection)
    assert set(sa.inspect(pg_connection).get_table_names()) == {"users", "locations", "predictions", "alerts"}


def test_empty_legacy_database_gets_required_columns_and_constraints(legacy):
    upgrade_location_schema(legacy)
    upgrade_location_schema(legacy)
    columns = {column["name"]: column for column in sa.inspect(legacy).get_columns("locations")}
    assert all(not columns[name]["nullable"] for name in ("slug", "division", "latitude", "longitude"))
    indexes = {index["name"]: index for index in sa.inspect(legacy).get_indexes("locations")}
    assert indexes["ix_locations_slug"]["unique"]
    with pytest.raises(sa.exc.IntegrityError), legacy.begin_nested():
        legacy.execute(sa.text(
            "INSERT INTO locations (name, slug, division, latitude, longitude) "
            "VALUES ('Invalid', 'invalid', 'CENTRAL', 91, 178)"
        ))


def test_upgrade_keeps_users_predictions_alerts_and_location_ids(legacy):
    legacy.execute(sa.text(
        "INSERT INTO users (id, name, email, hashed_password) "
        "VALUES (31, 'Migration fixture', 'fixture@example.com', 'test-only-value')"
    ))
    legacy.execute(sa.text("INSERT INTO locations (id, name, is_active) VALUES (42, 'Suva', false)"))
    legacy.execute(sa.text(
        "INSERT INTO predictions (id, location_id, risk_level, flood_probability, model_version, predicted_at) "
        "VALUES (43, 42, 'HIGH', 0.7, 'existing-real-prediction', CURRENT_TIMESTAMP)"
    ))
    legacy.execute(sa.text(
        "INSERT INTO alerts (id, location_id, prediction_id, severity, source, message, created_at) "
        "VALUES (44, 42, 43, 'HIGH', 'AI_RECOMMENDATION', 'Test-only existing alert', CURRENT_TIMESTAMP)"
    ))
    upgrade_location_schema(legacy)
    upgrade_location_schema(legacy)
    location = legacy.execute(sa.text("SELECT * FROM locations WHERE id=42")).mappings().one()
    assert (location["slug"], location["division"], location["latitude"], location["longitude"]) == (
        "suva", "CENTRAL", -18.1416, 178.4419,
    )
    assert location["is_active"] is False
    assert legacy.execute(sa.text("SELECT is_sample FROM predictions WHERE id=43")).scalar_one() is False
    assert legacy.execute(sa.text("SELECT prediction_id FROM alerts WHERE id=44")).scalar_one() == 43
    assert legacy.execute(sa.text("SELECT hashed_password FROM users WHERE id=31")).scalar_one() == "test-only-value"


def test_unknown_legacy_coordinates_are_not_invented(legacy):
    legacy.execute(sa.text("INSERT INTO locations (id, name) VALUES (42, 'Unknown site')"))
    with pytest.raises(RuntimeError, match="Location 42 needs"):
        upgrade_location_schema(legacy)
    assert {column["name"] for column in sa.inspect(legacy).get_columns("locations")} == {"id", "name", "is_active"}
    assert legacy.execute(sa.text("SELECT name FROM locations WHERE id=42")).scalar_one() == "Unknown site"


def test_failed_upgrade_rolls_back_without_losing_rows(legacy):
    legacy.execute(sa.text("INSERT INTO locations (name) VALUES ('Suva'), ('Suva')"))
    with pytest.raises(sa.exc.IntegrityError), legacy.begin_nested():
        upgrade_location_schema(legacy)
    assert legacy.execute(sa.text("SELECT count(*) FROM locations")).scalar_one() == 2
    assert "slug" not in {column["name"] for column in sa.inspect(legacy).get_columns("locations")}


def test_existing_coordinates_and_sample_flags_are_preserved(pg_connection):
    Base.metadata.create_all(pg_connection)
    pg_connection.execute(sa.text(
        "INSERT INTO locations (id, name, slug, division, latitude, longitude) "
        "VALUES (42, 'Custom site', 'custom-site', 'NORTHERN', -16.8, 179.9)"
    ))
    pg_connection.execute(sa.text(
        "INSERT INTO predictions (location_id, risk_level, flood_probability, model_version, predicted_at, is_sample) "
        "VALUES (42, 'HIGH', 0.7, 'sample-demo-not-a-model-result', CURRENT_TIMESTAMP, true)"
    ))
    upgrade_location_schema(pg_connection)
    assert pg_connection.execute(sa.text("SELECT latitude FROM locations WHERE id=42")).scalar_one() == -16.8
    assert pg_connection.execute(sa.text("SELECT is_sample FROM predictions")).scalar_one() is True
