import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.models.user import AccountStatus, User, UserRole


PENDING_URL = "/api/admin/users/pending"


def _authorization(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def _admin(user_factory) -> User:
    return user_factory(
        email="admin@example.com",
        name="MET Admin",
        role=UserRole.MET_ADMIN,
    )


def test_met_admin_can_access_admin_route(client: TestClient, user_factory):
    admin = _admin(user_factory)

    response = client.get(PENDING_URL, headers=_authorization(admin))

    assert response.status_code == 200


def test_community_user_cannot_access_admin_route(client: TestClient, user_factory):
    community_user = user_factory(email="community@example.com")

    response = client.get(PENDING_URL, headers=_authorization(community_user))

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


def test_admin_can_list_pending_users(client: TestClient, user_factory):
    admin = _admin(user_factory)
    pending = user_factory(
        email="pending@example.com",
        name="Pending User",
        account_status=AccountStatus.PENDING,
    )
    user_factory(email="approved@example.com")

    response = client.get(PENDING_URL, headers=_authorization(admin))

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": pending.id,
            "name": "Pending User",
            "email": "pending@example.com",
            "role": "COMMUNITY",
            "status": "PENDING",
        }
    ]


def test_admin_can_approve_pending_user(
    client: TestClient,
    session_factory,
    user_factory,
):
    admin = _admin(user_factory)
    pending = user_factory(
        email="approve@example.com",
        account_status=AccountStatus.PENDING,
    )

    response = client.patch(
        f"/api/admin/users/{pending.id}/approve",
        headers=_authorization(admin),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"
    assert set(response.json()) == {"id", "name", "email", "role", "status"}
    with session_factory() as session:
        assert session.get(User, pending.id).status == AccountStatus.APPROVED


def test_admin_can_reject_pending_user(
    client: TestClient,
    session_factory,
    user_factory,
):
    admin = _admin(user_factory)
    pending = user_factory(
        email="reject@example.com",
        account_status=AccountStatus.PENDING,
    )

    response = client.patch(
        f"/api/admin/users/{pending.id}/reject",
        headers=_authorization(admin),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert set(response.json()) == {"id", "name", "email", "role", "status"}
    with session_factory() as session:
        assert session.get(User, pending.id).status == AccountStatus.REJECTED


def test_community_user_cannot_approve_another_user(client: TestClient, user_factory):
    community_user = user_factory(email="community@example.com")
    pending = user_factory(
        email="pending@example.com",
        account_status=AccountStatus.PENDING,
    )

    response = client.patch(
        f"/api/admin/users/{pending.id}/approve",
        headers=_authorization(community_user),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


def test_approving_nonexistent_user_returns_404(client: TestClient, user_factory):
    admin = _admin(user_factory)

    response = client.patch(
        "/api/admin/users/999999/approve",
        headers=_authorization(admin),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}


@pytest.mark.parametrize(
    ("current_status", "action", "message"),
    [
        (AccountStatus.APPROVED, "approve", "Account is already approved"),
        (AccountStatus.APPROVED, "reject", "Account is already approved"),
        (AccountStatus.REJECTED, "approve", "Account has already been rejected"),
        (AccountStatus.REJECTED, "reject", "Account has already been rejected"),
    ],
)
def test_terminal_account_transition_returns_conflict(
    client: TestClient,
    user_factory,
    current_status: AccountStatus,
    action: str,
    message: str,
):
    admin = _admin(user_factory)
    target = user_factory(
        email="terminal@example.com",
        account_status=current_status,
    )

    response = client.patch(
        f"/api/admin/users/{target.id}/{action}",
        headers=_authorization(admin),
    )

    assert response.status_code == 409
    assert response.json() == {"detail": message}
