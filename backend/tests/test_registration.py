from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models.user import User


VALID_USER = {
    "name": "Parvish Mohan",
    "email": "parvish@example.com",
    "password": "FloodRisk123!",
    "role": "COMMUNITY",
}


def test_successful_registration(client: TestClient):
    response = client.post("/api/auth/register", json=VALID_USER)

    assert response.status_code == 201
    assert response.json() == {
        "id": 1,
        "name": "Parvish Mohan",
        "email": "parvish@example.com",
        "role": "COMMUNITY",
        "status": "PENDING",
    }


def test_duplicate_email_returns_conflict(client: TestClient):
    first_response = client.post("/api/auth/register", json=VALID_USER)
    duplicate = {**VALID_USER, "email": "PARVISH@example.com"}
    second_response = client.post("/api/auth/register", json=duplicate)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json() == {"detail": "Account already exists"}


def test_invalid_email_is_rejected(client: TestClient):
    response = client.post(
        "/api/auth/register",
        json={**VALID_USER, "email": "not-an-email"},
    )

    assert response.status_code == 422


def test_short_password_is_rejected(client: TestClient):
    response = client.post(
        "/api/auth/register",
        json={**VALID_USER, "password": "short"},
    )

    assert response.status_code == 422


def test_plaintext_password_is_not_stored(client: TestClient, db: Session):
    response = client.post("/api/auth/register", json=VALID_USER)
    stored_user = db.scalar(select(User).where(User.email == VALID_USER["email"]))

    assert response.status_code == 201
    assert stored_user is not None
    assert stored_user.hashed_password != VALID_USER["password"]
    assert verify_password(VALID_USER["password"], stored_user.hashed_password)


def test_hashed_password_is_not_returned(client: TestClient):
    response = client.post("/api/auth/register", json=VALID_USER)

    assert response.status_code == 201
    assert "hashed_password" not in response.json()
    assert "password" not in response.json()
