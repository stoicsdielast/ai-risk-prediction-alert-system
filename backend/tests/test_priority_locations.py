import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.routes import priority_locations as priority_routes
from app.core.security import create_access_token
from app.db.seed_locations import seed_demo_locations
from app.models import AccountStatus, Location, PriorityLocation, User, UserRole
from app.services.location_service import LocationServiceError


PRIORITY_URL = "/api/me/priority-locations"


def authorization(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
def seeded(session_factory):
    with session_factory() as session:
        seed_demo_locations(session)


@pytest.fixture
def community_user(user_factory):
    return user_factory(email="community@example.com")


def _slugs(response) -> list[str]:
    return [location["slug"] for location in response.json()]


def _save(client, user, slug):
    return client.put(f"{PRIORITY_URL}/{slug}", headers=authorization(user))


def test_list_is_empty_before_anything_is_saved(client: TestClient, seeded, community_user):
    response = client.get(PRIORITY_URL, headers=authorization(community_user))

    assert response.status_code == 200
    assert response.json() == []


def test_community_user_can_save_a_location(client: TestClient, seeded, community_user):
    response = _save(client, community_user, "suva")

    assert response.status_code == 200
    assert response.json()["slug"] == "suva"
    assert response.json()["division_label"] == "Central Division"
    assert response.json()["prediction"]["is_sample"] is True
    assert _slugs(client.get(PRIORITY_URL, headers=authorization(community_user))) == ["suva"]


def test_saved_locations_are_ordered_by_name(client: TestClient, seeded, community_user):
    for slug in ("suva", "labasa", "nadi"):
        _save(client, community_user, slug)

    response = client.get(PRIORITY_URL, headers=authorization(community_user))

    assert _slugs(response) == ["labasa", "nadi", "suva"]


def test_saving_twice_keeps_one_entry(client: TestClient, seeded, community_user, db):
    assert _save(client, community_user, "suva").status_code == 200
    assert _save(client, community_user, "suva").status_code == 200

    assert db.scalar(select(func.count(PriorityLocation.id))) == 1


def test_users_only_see_their_own_priority_locations(
    client: TestClient, seeded, community_user, user_factory,
):
    other_user = user_factory(email="neighbour@example.com")
    _save(client, community_user, "suva")
    _save(client, other_user, "labasa")

    assert _slugs(client.get(PRIORITY_URL, headers=authorization(community_user))) == ["suva"]
    assert _slugs(client.get(PRIORITY_URL, headers=authorization(other_user))) == ["labasa"]


def test_met_admin_can_also_save_locations(client: TestClient, seeded, user_factory):
    admin = user_factory(email="met-admin@example.com", role=UserRole.MET_ADMIN)

    assert _save(client, admin, "nadi").status_code == 200


def test_remove_a_saved_location(client: TestClient, seeded, community_user):
    _save(client, community_user, "suva")
    _save(client, community_user, "nadi")

    response = client.delete(f"{PRIORITY_URL}/suva", headers=authorization(community_user))

    assert response.status_code == 204
    assert _slugs(client.get(PRIORITY_URL, headers=authorization(community_user))) == ["nadi"]


def test_removing_an_unsaved_location_is_a_no_op(client: TestClient, seeded, community_user):
    response = client.delete(f"{PRIORITY_URL}/suva", headers=authorization(community_user))

    assert response.status_code == 204


def test_removing_does_not_affect_other_users(
    client: TestClient, seeded, community_user, user_factory,
):
    other_user = user_factory(email="neighbour@example.com")
    _save(client, community_user, "suva")
    _save(client, other_user, "suva")

    client.delete(f"{PRIORITY_URL}/suva", headers=authorization(community_user))

    assert _slugs(client.get(PRIORITY_URL, headers=authorization(other_user))) == ["suva"]


@pytest.mark.parametrize("method", ["put", "delete"])
def test_unknown_location_returns_404(client: TestClient, seeded, community_user, method):
    response = getattr(client, method)(
        f"{PRIORITY_URL}/atlantis", headers=authorization(community_user),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Location not found"}


def test_inactive_location_cannot_be_saved_but_can_be_removed(
    client: TestClient, seeded, community_user, db,
):
    _save(client, community_user, "labasa")
    labasa = db.scalar(select(Location).where(Location.slug == "labasa"))
    labasa.is_active = False
    db.commit()

    assert client.get(PRIORITY_URL, headers=authorization(community_user)).json() == []
    assert _save(client, community_user, "labasa").status_code == 404
    response = client.delete(f"{PRIORITY_URL}/labasa", headers=authorization(community_user))
    assert response.status_code == 204
    assert db.scalar(select(func.count(PriorityLocation.id))) == 0


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", PRIORITY_URL), ("put", f"{PRIORITY_URL}/suva"), ("delete", f"{PRIORITY_URL}/suva")],
)
def test_priority_locations_require_authentication(client: TestClient, seeded, method, path):
    response = getattr(client, method)(path)

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("account_status", "active"),
    [(AccountStatus.PENDING, True), (AccountStatus.REJECTED, True), (AccountStatus.APPROVED, False)],
)
def test_unapproved_or_inactive_accounts_cannot_save(
    client: TestClient, seeded, user_factory, account_status, active,
):
    user = user_factory(email="blocked@example.com", account_status=account_status, is_active=active)

    assert _save(client, user, "suva").status_code == 403


def test_database_error_returns_safe_500(client: TestClient, community_user, monkeypatch):
    def failing_list(*args, **kwargs):
        raise LocationServiceError

    monkeypatch.setattr(priority_routes, "list_priority_locations", failing_list)

    response = client.get(PRIORITY_URL, headers=authorization(community_user))

    assert response.status_code == 500
    assert response.json() == {"detail": "Unable to update priority locations"}


def test_duplicate_is_rejected_when_service_is_bypassed(db, seeded, community_user):
    suva_id = db.scalar(select(Location.id).where(Location.slug == "suva"))
    db.add(PriorityLocation(user_id=community_user.id, location_id=suva_id))
    db.commit()
    db.add(PriorityLocation(user_id=community_user.id, location_id=suva_id))

    with pytest.raises(IntegrityError):
        db.commit()


def test_deleting_a_user_removes_their_priority_locations(db, seeded, community_user):
    suva_id = db.scalar(select(Location.id).where(Location.slug == "suva"))
    db.add(PriorityLocation(user_id=community_user.id, location_id=suva_id))
    db.commit()

    db.delete(db.get(User, community_user.id))
    db.commit()

    assert db.scalar(select(func.count(PriorityLocation.id))) == 0
