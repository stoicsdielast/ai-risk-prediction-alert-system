"""Versioned migrations; database credentials come from existing app settings."""
from alembic import context
from app import models  # noqa: F401
from app.db.base import Base
from app.db.session import get_engine

with get_engine().connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
