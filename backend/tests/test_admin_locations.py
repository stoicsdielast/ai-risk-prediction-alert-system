"""Administrator location management (create/update/deactivate).

Covers ticket LO-02: protected administrator create/update operations with
slug-uniqueness and field validation, deactivation that preserves history, and
public reads that exclude deactivated locations.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.location import Division, Location
from app.models.prediction import Prediction
from app.models.risk import RiskLevel
from app.models.user import UserRole
from app.db.seed_locations import seed_demo_locations


ADMIN_LOCATIONS_URL = "/api/admin/locations"
PUBLIC_LOCATIONS_URL = "/api/locations"


def new_location_payload(**kwargs):
    payload = {
        "name": "Test Only — Vatuwaqa",
        "slug": "vatuwaqa",
        "division": "CENTRAL",
        "latitude": -18.15,
        "longitude": 178.45,
    }
    payload.update(kwargs)
    return payload


def sample_prediction(session_factory, location_id: int) -> None:
    with session_factory() as session:
        session.add(
            Prediction(
                location_id=location_id,
                risk_level=RiskLevel.MODERATE,
                flood_probability=0.5,
                model_version="test-controlled-fixture",
                predicted_at=datetime.now(timezone.utc),
                is_sample=True,
            )
        )
        session.commit()


class AdminClient:
    def __init__(self, client: TestClient, headers: dict[str, str]):
        self.client = client
        self.headers = headers


@pytest.fixture
def admin(client: TestClient, user_factory) -> AdminClient:
    user_factory(email="loc-admin@example.com", role=UserRole.MET_ADMIN)
    response = client.post(
        "/api/auth/login",
        json={"email": "loc-admin@example.com", "password": "Password123!"},
    )
    return AdminClient(client, {"Authorization": f"Bearer {response.json()['access_token']}"})


def test_create_requires_authentication(client: TestClient):
    response = client.post(ADMIN_LOCATIONS_URL, json=new_location_payload())

    assert response.status_code == 401


def test_create_rejects_non_admin(client: TestClient, user_factory):
    user_factory(email="loc-community@example.com", role=UserRole.COMMUNITY)
    login = client.post(
        "/api/auth/login",
        json={"email": "loc-community@example.com", "password": "Password123!"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post(ADMIN_LOCATIONS_URL, json=new_location_payload(), headers=headers)

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


def test_create_returns_201_with_full_body(admin: AdminClient, db):
    response = admin.client.post(
        ADMIN_LOCATIONS_URL, json=new_location_payload(), headers=admin.headers
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert isinstance(body["id"], int)
    assert body["slug"] == "vatuwaqa"
    assert body["division"] == "CENTRAL"
    assert body["division_label"] == "Central Division"
    assert body["prediction"] is None
    location = db.get(Location, body["id"])
    assert location.is_active is True


def test_create_duplicate_slug_is_conflict(admin: AdminClient, client: TestClient, db):
    seed_demo_locations(db)
    response = admin.client.post(
        ADMIN_LOCATIONS_URL,
        json=new_location_payload(slug="suva", name="Suva duplicate"),
        headers=admin.headers,
    )

    assert response.status_code == 409
    assert "slug" in response.json()["detail"].lower()


def test_create_strips_surrounding_whitespace(admin: AdminClient, db):
    response = admin.client.post(
        ADMIN_LOCATIONS_URL,
        json=new_location_payload(name="  Test Only — Vatuwaqa  "),
        headers=admin.headers,
    )

    assert response.status_code == 201
    assert db.get(Location, response.json()["id"]).name == "Test Only — Vatuwaqa"


def test_create_whitespace_only_name_is_rejected(admin: AdminClient):
    response = admin.client.post(
        ADMIN_LOCATIONS_URL, json=new_location_payload(name="   "), headers=admin.headers
    )

    assert response.status_code == 422


def test_create_blank_name_is_rejected(admin: AdminClient):
    response = admin.client.post(
        ADMIN_LOCATIONS_URL, json=new_location_payload(name=""), headers=admin.headers
    )

    assert response.status_code == 422


def test_create_out_of_range_coordinates_are_rejected(admin: AdminClient):
    for latitude, longitude in ((-91.0, 178.0), (91.0, 178.0), (-18.0, -181.0), (-18.0, 181.0)):
        response = admin.client.post(
            ADMIN_LOCATIONS_URL,
            json=new_location_payload(latitude=latitude, longitude=longitude),
            headers=admin.headers,
        )
        assert response.status_code == 422


def test_create_invalid_division_is_rejected(admin: AdminClient):
    response = admin.client.post(
        ADMIN_LOCATIONS_URL, json=new_location_payload(division="SOUTHERN"), headers=admin.headers
    )

    assert response.status_code == 422


def test_create_invalid_slug_format_is_rejected(admin: AdminClient):
    for slug in ("Suva", "with_underscore", "-leading", "trailing-", "a b"):
        response = admin.client.post(
            ADMIN_LOCATIONS_URL, json=new_location_payload(slug=slug), headers=admin.headers
        )
        assert response.status_code == 422, slug


def test_create_unknown_field_is_rejected(admin: AdminClient):
    response = admin.client.post(
        ADMIN_LOCATIONS_URL,
        json=new_location_payload(extra_surprise=True),
        headers=admin.headers,
    )

    assert response.status_code == 422


def test_update_edits_fields_and_public_read_reflects_changes(admin: AdminClient, db):
    created = admin.client.post(
        ADMIN_LOCATIONS_URL, json=new_location_payload(), headers=admin.headers
    ).json()

    response = admin.client.patch(
        f"{ADMIN_LOCATIONS_URL}/{created['id']}",
        json={
            "name": "Renamed Test Location",
            "division": "WESTERN",
            "latitude": -17.78,
            "longitude": 177.44,
        },
        headers=admin.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Renamed Test Location"
    assert body["division"] == "WESTERN"
    assert body["latitude"] == -17.78
    assert body["longitude"] == 177.44
    assert body["is_active"] is True

    public = admin.client.get(f"{PUBLIC_LOCATIONS_URL}/vatuwaqa")
    assert public.status_code == 200
    assert public.json()["name"] == "Renamed Test Location"


def test_update_slug_is_immutable(admin: AdminClient):
    created = admin.client.post(
        ADMIN_LOCATIONS_URL, json=new_location_payload(), headers=admin.headers
    ).json()

    response = admin.client.patch(
        f"{ADMIN_LOCATIONS_URL}/{created['id']}", json={"slug": "new-slug"}, headers=admin.headers
    )

    assert response.status_code == 422


def test_update_empty_body_is_rejected(admin: AdminClient):
    created = admin.client.post(
        ADMIN_LOCATIONS_URL, json=new_location_payload(), headers=admin.headers
    ).json()

    response = admin.client.patch(
        f"{ADMIN_LOCATIONS_URL}/{created['id']}", json={}, headers=admin.headers
    )

    assert response.status_code == 422


def test_update_explicit_null_is_rejected(admin: AdminClient):
    created = admin.client.post(
        ADMIN_LOCATIONS_URL, json=new_location_payload(), headers=admin.headers
    ).json()

    response = admin.client.patch(
        f"{ADMIN_LOCATIONS_URL}/{created['id']}", json={"name": None}, headers=admin.headers
    )

    assert response.status_code == 422


def test_update_unknown_location_is_404(admin: AdminClient):
    response = admin.client.patch(
        f"{ADMIN_LOCATIONS_URL}/999999", json={"name": "Ghost"}, headers=admin.headers
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Location not found"}


def test_update_requires_auth(client: TestClient):
    response = client.patch(f"{ADMIN_LOCATIONS_URL}/1", json={"name": "Nope"})

    assert response.status_code == 401


def test_deactivation_preserves_row_and_history(
    admin: AdminClient, session_factory, db
):
    created = admin.client.post(
        ADMIN_LOCATIONS_URL, json=new_location_payload(), headers=admin.headers
    ).json()
    sample_prediction(session_factory, created["id"])

    response = admin.client.patch(
        f"{ADMIN_LOCATIONS_URL}/{created['id']}", json={"is_active": False}, headers=admin.headers
    )

    assert response.status_code == 200
    location = db.get(Location, created["id"])
    assert location is not None and location.is_active is False
    # Prediction history survives deactivation.
    assert db.scalar(select(Prediction).where(Prediction.location_id == created["id"])) is not None


def test_deactivated_location_is_hidden_from_public_reads(admin: AdminClient):
    created = admin.client.post(
        ADMIN_LOCATIONS_URL, json=new_location_payload(), headers=admin.headers
    ).json()
    admin.client.patch(
        f"{ADMIN_LOCATIONS_URL}/{created['id']}", json={"is_active": False}, headers=admin.headers
    )

    public_list = admin.client.get(PUBLIC_LOCATIONS_URL)
    assert public_list.status_code == 200
    assert all(item["slug"] != "vatuwaqa" for item in public_list.json())

    assert admin.client.get(f"{PUBLIC_LOCATIONS_URL}/vatuwaqa").status_code == 404


def test_deactivated_location_rejects_new_weather_writes(admin: AdminClient):
    created = admin.client.post(
        ADMIN_LOCATIONS_URL, json=new_location_payload(), headers=admin.headers
    ).json()
    admin.client.patch(
        f"{ADMIN_LOCATIONS_URL}/{created['id']}", json={"is_active": False}, headers=admin.headers
    )

    response = admin.client.post(
        "/api/admin/weather/observations",
        json={
            "location_id": created["id"],
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "source": "test-gauge",
            "rainfall_mm": 10,
            "rainfall_period_minutes": 60,
        },
        headers=admin.headers,
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Location is inactive"}


def test_reactivation_restores_public_visibility(admin: AdminClient):
    created = admin.client.post(
        ADMIN_LOCATIONS_URL, json=new_location_payload(), headers=admin.headers
    ).json()
    admin.client.patch(
        f"{ADMIN_LOCATIONS_URL}/{created['id']}", json={"is_active": False}, headers=admin.headers
    )

    response = admin.client.patch(
        f"{ADMIN_LOCATIONS_URL}/{created['id']}", json={"is_active": True}, headers=admin.headers
    )

    assert response.status_code == 200
    assert admin.client.get(f"{PUBLIC_LOCATIONS_URL}/vatuwaqa").status_code == 200


def test_update_does_not_touch_other_fields(admin: AdminClient, db):
    created = admin.client.post(
        ADMIN_LOCATIONS_URL,
        json=new_location_payload(latitude=-18.15, longitude=178.45),
        headers=admin.headers,
    ).json()

    response = admin.client.patch(
        f"{ADMIN_LOCATIONS_URL}/{created['id']}", json={"name": "Renamed"}, headers=admin.headers
    )

    assert response.status_code == 200
    location = db.get(Location, created["id"])
    assert location.name == "Renamed"
    assert location.latitude == -18.15
    assert location.longitude == 178.45
    assert location.division == Division.CENTRAL
    assert location.is_active is True
