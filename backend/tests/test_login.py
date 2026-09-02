import jwt
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.models.user import AccountStatus


LOGIN_URL = "/api/auth/login"
PASSWORD = "Password123!"


def test_approved_user_can_log_in(client: TestClient, user_factory):
    user_factory(email="approved@example.com", password=PASSWORD)

    response = client.post(
        LOGIN_URL,
        json={"email": "approved@example.com", "password": PASSWORD},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]


def test_wrong_password_returns_401(client: TestClient, user_factory):
    user_factory(email="approved@example.com", password=PASSWORD)

    response = client.post(
        LOGIN_URL,
        json={"email": "approved@example.com", "password": "WrongPassword!"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}


def test_unknown_email_returns_401(client: TestClient):
    response = client.post(
        LOGIN_URL,
        json={"email": "unknown@example.com", "password": PASSWORD},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}


def test_pending_user_cannot_log_in(client: TestClient, user_factory):
    user_factory(
        email="pending@example.com",
        password=PASSWORD,
        account_status=AccountStatus.PENDING,
    )

    response = client.post(
        LOGIN_URL,
        json={"email": "pending@example.com", "password": PASSWORD},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Account approval pending"}


def test_rejected_user_cannot_log_in(client: TestClient, user_factory):
    user_factory(
        email="rejected@example.com",
        password=PASSWORD,
        account_status=AccountStatus.REJECTED,
    )

    response = client.post(
        LOGIN_URL,
        json={"email": "rejected@example.com", "password": PASSWORD},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Account has been rejected"}


def test_inactive_user_cannot_log_in(client: TestClient, user_factory):
    user_factory(
        email="inactive@example.com",
        password=PASSWORD,
        is_active=False,
    )

    response = client.post(
        LOGIN_URL,
        json={"email": "inactive@example.com", "password": PASSWORD},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Account is inactive"}


def test_successful_login_jwt_has_only_safe_required_claims(
    client: TestClient,
    user_factory,
):
    user = user_factory(email="jwt@example.com", password=PASSWORD)

    response = client.post(
        LOGIN_URL,
        json={"email": "jwt@example.com", "password": PASSWORD},
    )

    assert response.status_code == 200
    settings = get_settings()
    payload = jwt.decode(
        response.json()["access_token"],
        settings.jwt_secret_key.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
    )
    assert set(payload) == {"sub", "exp"}
    assert payload["sub"] == str(user.id)
