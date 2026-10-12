from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.routes import locations as locations_routes
from app.db.seed_locations import DEMO_LOCATIONS, seed_demo_locations
from app.models.location import Division, Location
from app.models.prediction import PredictionSource, RiskLevel, RiskPrediction
from app.services.location_service import LocationServiceError


LOCATIONS_URL = "/api/locations"


@pytest.fixture
def seeded(session_factory):
    with session_factory() as session:
        seed_demo_locations(session)


def _names(response) -> list[str]:
    return [location["name"] for location in response.json()]


def test_list_locations_is_empty_before_seeding(client: TestClient):
    response = client.get(LOCATIONS_URL)

    assert response.status_code == 200
    assert response.json() == []


def test_list_locations_returns_coordinates_and_division(client: TestClient, seeded):
    response = client.get(LOCATIONS_URL)

    assert response.status_code == 200
    assert len(response.json()) == len(DEMO_LOCATIONS)
    suva = next(item for item in response.json() if item["slug"] == "suva")
    suva.pop("prediction")
    assert suva == {
        "slug": "suva",
        "name": "Suva",
        "division": "CENTRAL",
        "division_label": "Central Division",
        "latitude": -18.1416,
        "longitude": 178.4419,
    }


def test_list_locations_is_ordered_by_name(client: TestClient, seeded):
    names = _names(client.get(LOCATIONS_URL))

    assert names == sorted(names)


def test_list_locations_does_not_require_authentication(client: TestClient, seeded):
    response = client.get(LOCATIONS_URL)

    assert response.status_code == 200


def test_filter_locations_by_division(client: TestClient, seeded):
    response = client.get(LOCATIONS_URL, params={"division": "NORTHERN"})

    assert response.status_code == 200
    assert _names(response) == ["Labasa", "Savusavu"]


def test_invalid_division_is_rejected(client: TestClient):
    response = client.get(LOCATIONS_URL, params={"division": "SOUTHERN"})

    assert response.status_code == 422


def test_search_is_case_insensitive_partial_match(client: TestClient, seeded):
    response = client.get(LOCATIONS_URL, params={"search": "  sUv "})

    assert response.status_code == 200
    assert _names(response) == ["Suva"]


def test_search_and_division_combine(client: TestClient, seeded):
    response = client.get(
        LOCATIONS_URL,
        params={"search": "a", "division": "EASTERN"},
    )

    assert _names(response) == ["Levuka", "Vunisea (Kadavu)"]


def test_search_treats_wildcards_literally(client: TestClient, seeded):
    response = client.get(LOCATIONS_URL, params={"search": "%"})

    assert response.status_code == 200
    assert response.json() == []


def test_overlong_search_is_rejected(client: TestClient):
    response = client.get(LOCATIONS_URL, params={"search": "x" * 101})

    assert response.status_code == 422


def test_get_location_by_slug(client: TestClient, seeded):
    response = client.get(f"{LOCATIONS_URL}/labasa")

    assert response.status_code == 200
    assert response.json()["name"] == "Labasa"
    assert response.json()["division_label"] == "Northern Division"


def test_unknown_location_returns_404(client: TestClient, seeded):
    response = client.get(f"{LOCATIONS_URL}/atlantis")

    assert response.status_code == 404
    assert response.json() == {"detail": "Location not found"}


def test_list_divisions(client: TestClient):
    response = client.get(f"{LOCATIONS_URL}/divisions")

    assert response.status_code == 200
    assert response.json() == [
        {"code": "CENTRAL", "label": "Central Division"},
        {"code": "WESTERN", "label": "Western Division"},
        {"code": "NORTHERN", "label": "Northern Division"},
        {"code": "EASTERN", "label": "Eastern Division"},
    ]


def test_database_error_returns_safe_500(client: TestClient, monkeypatch):
    def failing_list_locations(*args, **kwargs):
        raise LocationServiceError

    monkeypatch.setattr(locations_routes, "list_locations", failing_list_locations)

    response = client.get(LOCATIONS_URL)

    assert response.status_code == 500
    assert response.json() == {"detail": "Unable to retrieve locations"}


def test_demo_locations_cover_every_division():
    assert {demo.division for demo in DEMO_LOCATIONS} == set(Division)


def test_demo_location_slugs_are_unique():
    slugs = [demo.slug for demo in DEMO_LOCATIONS]

    assert len(slugs) == len(set(slugs))


def test_seeding_is_repeatable(db):
    first = seed_demo_locations(db)
    second = seed_demo_locations(db)

    assert (first.created, first.updated) == (len(DEMO_LOCATIONS), 0)
    assert (second.created, second.updated) == (0, len(DEMO_LOCATIONS))
    assert db.scalar(select(func.count(Location.id))) == len(DEMO_LOCATIONS)


def test_seeding_restores_edited_demo_values(db):
    seed_demo_locations(db)
    suva = db.scalar(select(Location).where(Location.slug == "suva"))
    suva.latitude = 0.0
    db.commit()

    seed_demo_locations(db)

    db.refresh(suva)
    assert suva.latitude == -18.1416


def test_seeding_leaves_other_locations_untouched(db):
    db.add(
        Location(
            slug="taveuni",
            name="Taveuni",
            division=Division.NORTHERN,
            latitude=-16.85,
            longitude=179.95,
        )
    )
    db.commit()

    seed_demo_locations(db)

    assert db.scalar(select(Location).where(Location.slug == "taveuni")) is not None
    assert db.scalar(select(func.count(Location.id))) == len(DEMO_LOCATIONS) + 1


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(-91.0, 178.0), (91.0, 178.0), (-18.0, -181.0), (-18.0, 181.0)],
)
def test_out_of_range_coordinates_are_rejected(db, latitude, longitude):
    db.add(
        Location(
            slug="invalid",
            name="Invalid",
            division=Division.CENTRAL,
            latitude=latitude,
            longitude=longitude,
        )
    )

    with pytest.raises(IntegrityError):
        db.commit()


def test_duplicate_slug_is_rejected(db):
    seed_demo_locations(db)
    db.add(
        Location(
            slug="suva",
            name="Suva duplicate",
            division=Division.CENTRAL,
            latitude=-18.1,
            longitude=178.4,
        )
    )

    with pytest.raises(IntegrityError):
        db.commit()


def _location_id(db, slug: str) -> int:
    return db.scalar(select(Location.id).where(Location.slug == slug))


def _add_prediction(db, slug: str, **overrides) -> RiskPrediction:
    values = {
        "location_id": _location_id(db, slug),
        "risk_level": RiskLevel.LOW,
        "confidence_percent": 50,
        "label": "Test prediction",
        "summary": "Test summary",
        "source": PredictionSource.MODEL,
        **overrides,
    }
    prediction = RiskPrediction(**values)
    db.add(prediction)
    db.commit()
    return prediction


def test_location_with_sample_risk_is_labelled_as_sample(client: TestClient, seeded):
    response = client.get(f"{LOCATIONS_URL}/suva")

    prediction = response.json()["prediction"]
    generated_at = prediction.pop("generated_at")
    assert generated_at
    assert prediction == {
        "risk_level": "MODERATE",
        "confidence_percent": 78,
        "label": "Elevated urban flood potential",
        "summary": (
            "Drainage pressure may increase if rainfall persists for another 2–3 hours."
        ),
        "source": "SAMPLE",
        "is_sample": True,
    }


def test_location_without_prediction_returns_null(client: TestClient, seeded):
    response = client.get(f"{LOCATIONS_URL}/navua")

    assert response.status_code == 200
    assert response.json()["prediction"] is None


def test_list_includes_predictions_only_where_available(client: TestClient, seeded):
    response = client.get(LOCATIONS_URL)

    with_prediction = {
        item["slug"] for item in response.json() if item["prediction"] is not None
    }
    expected = {demo.slug for demo in DEMO_LOCATIONS if demo.sample_risk is not None}
    assert with_prediction == expected
    assert {"navua", "rakiraki", "levuka", "vunisea"}.isdisjoint(with_prediction)


def test_latest_prediction_is_returned(client: TestClient, seeded, db):
    _add_prediction(
        db,
        "suva",
        risk_level=RiskLevel.VERY_HIGH,
        generated_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    prediction = client.get(f"{LOCATIONS_URL}/suva").json()["prediction"]

    assert prediction["risk_level"] == "VERY_HIGH"
    assert prediction["source"] == "MODEL"
    assert prediction["is_sample"] is False


def test_seeding_does_not_duplicate_sample_risks(db):
    first = seed_demo_locations(db)
    seed_demo_locations(db)

    count = db.scalar(select(func.count(RiskPrediction.id)))
    assert first.sample_risks == count
    assert count == sum(demo.sample_risk is not None for demo in DEMO_LOCATIONS)


def test_seeding_keeps_model_predictions(db):
    seed_demo_locations(db)
    model_prediction = _add_prediction(db, "navua")

    seed_demo_locations(db)

    assert db.get(RiskPrediction, model_prediction.id) is not None


def test_seeding_restores_edited_sample_risk(db):
    seed_demo_locations(db)
    sample = db.scalar(
        select(RiskPrediction).where(
            RiskPrediction.location_id == _location_id(db, "nadi")
        )
    )
    sample.risk_level = RiskLevel.LOW
    db.commit()

    seed_demo_locations(db)

    restored = db.scalar(
        select(RiskPrediction).where(
            RiskPrediction.location_id == _location_id(db, "nadi")
        )
    )
    assert restored.risk_level == RiskLevel.VERY_HIGH


def test_demo_set_includes_locations_without_sample_risk():
    assert any(demo.sample_risk is None for demo in DEMO_LOCATIONS)
    assert any(demo.sample_risk is not None for demo in DEMO_LOCATIONS)


@pytest.mark.parametrize("confidence", [-1, 101])
def test_out_of_range_confidence_is_rejected(db, confidence):
    seed_demo_locations(db)

    with pytest.raises(IntegrityError):
        _add_prediction(db, "navua", confidence_percent=confidence)
