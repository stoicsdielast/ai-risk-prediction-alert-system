from app import models  # noqa: F401 -- registers models with Base metadata
from app.db.base import Base
from app.db.session import get_engine


def create_tables() -> None:
    Base.metadata.create_all(bind=get_engine())


if __name__ == "__main__":
    create_tables()
