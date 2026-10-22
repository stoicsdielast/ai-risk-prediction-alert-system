import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import AccountStatus, User, UserRole


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    monkeypatch.setenv("ALERT_DEMO_ENABLED", "false")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://test:test@localhost/test",
    )
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "test-only-secret-key-with-at-least-32-characters",
    )
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enforce_foreign_keys(connection, _record):
        # Explicit BEGIN also makes savepoint rollback match PostgreSQL semantics.
        connection.isolation_level = None
        connection.execute("PRAGMA foreign_keys=ON")

    @event.listens_for(engine, "begin")
    def begin_transaction(connection):
        connection.exec_driver_sql("BEGIN")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(session_factory):
    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def db(session_factory) -> Session:
    with session_factory() as session:
        yield session


@pytest.fixture
def user_factory(session_factory):
    def create_user(
        *,
        email: str,
        password: str = "Password123!",
        name: str = "Test User",
        role: UserRole = UserRole.COMMUNITY,
        account_status: AccountStatus = AccountStatus.APPROVED,
        is_active: bool = True,
    ) -> User:
        with session_factory() as session:
            user = User(
                name=name,
                email=email.lower(),
                hashed_password=hash_password(password),
                role=role,
                status=account_status,
                is_active=is_active,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return user

    return create_user
