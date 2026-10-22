from app import models  # noqa: F401 -- registers models with Base metadata
from app.db.base import Base
from app.db.migrate_locations import upgrade_location_schema
from app.db.session import get_engine


def create_tables() -> None:
    with get_engine().begin() as connection:
        upgrade_location_schema(connection)
        Base.metadata.create_all(bind=connection, tables=[t for t in Base.metadata.sorted_tables if not t.name.startswith("synthetic_")])


if __name__ == "__main__":
    create_tables()
