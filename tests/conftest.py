import pytest
from sqlalchemy.orm import sessionmaker

from app.storage.db import create_all, make_engine, make_session_factory


@pytest.fixture
def session_factory() -> sessionmaker:
    """Hermetic in-memory SQLite DB with schema created, fresh per test."""
    engine = make_engine("sqlite://")
    create_all(engine)
    return make_session_factory(engine)
