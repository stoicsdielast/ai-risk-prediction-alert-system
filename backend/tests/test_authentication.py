from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.models.user import AccountStatus, User


ME_URL = "/api/auth/me"


def _authorization(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_valid_token_accesses_protected_endpoint(client: TestClient, user_factory):
    user = user_factory(email="protected@example.com")
    token = create_access_token(user.id)

    response = client.get(ME_URL, headers=_authorization(token))

    assert response.status_code == 200


def test_missing_token_returns_401(client: TestClient):
    response = client.get(ME_URL)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_malformed_token_returns_401(client: TestClient):
    response = client.get(ME_URL, headers=_authorization("not.a.valid.jwt"))

    assert response.status_code == 401


def test_expired_token_returns_401(client: TestClient, user_factory):
    user = user_factory(email="expired@example.com")
    token = create_access_token(user.id, expires_delta=timedelta(seconds=-1))

    response = client.get(ME_URL, headers=_authorization(token))

    assert response.status_code == 401


def test_me_returns_authenticated_user(client: TestClient, user_factory):
    user = user_factory(email="current@example.com", name="Current User")
    token = create_access_token(user.id)

    response = client.get(ME_URL, headers=_authorization(token))

    assert response.status_code == 200
    assert response.json() == {
        "id": user.id,
        "name": "Current User",
        "email": "current@example.com",
        "role": "COMMUNITY",
        "status": "APPROVED",
    }


def test_me_does_not_return_password_hash(client: TestClient, user_factory):
    user = user_factory(email="safe-response@example.com")
    token = create_access_token(user.id)

    response = client.get(ME_URL, headers=_authorization(token))

    assert response.status_code == 200
    assert "hashed_password" not in response.json()
    assert "password" not in response.json()


def test_disabling_user_invalidates_existing_token(
    client: TestClient,
    session_factory,
    user_factory,
):
    user = user_factory(email="disabled-later@example.com")
    token = create_access_token(user.id)

    with session_factory() as session:
        stored_user = session.get(User, user.id)
        assert stored_user is not None
        stored_user.is_active = False
        session.commit()

    response = client.get(ME_URL, headers=_authorization(token))

    assert response.status_code == 403
    assert response.json() == {"detail": "Account is inactive"}


@pytest.mark.parametrize(
    ("new_status", "message"),
    [
        (AccountStatus.PENDING, "Account approval pending"),
        (AccountStatus.REJECTED, "Account has been rejected"),
    ],
)
def test_account_status_change_invalidates_existing_token(
    client: TestClient,
    session_factory,
    user_factory,
    new_status: AccountStatus,
    message: str,
):
    user = user_factory(email=f"changed-{new_status.value.lower()}@example.com")
    token = create_access_token(user.id)

    with session_factory() as session:
        stored_user = session.get(User, user.id)
        assert stored_user is not None
        stored_user.status = new_status
        session.commit()

    response = client.get(ME_URL, headers=_authorization(token))

    assert response.status_code == 403
    assert response.json() == {"detail": message}
