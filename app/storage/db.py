"""Engine/session helpers. Defaults to SQLite (zero setup); Postgres via DATABASE_URL."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ..config import get_settings
from .models import Base


def make_engine(url: str | None = None) -> Engine:
    url = url or get_settings().resolved_database_url()
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        # In-memory DBs need a single shared connection or the schema vanishes between sessions.
        if url in ("sqlite://", "sqlite:///:memory:"):
            return create_engine(
                url, connect_args=connect_args, poolclass=StaticPool, future=True
            )
        return create_engine(url, connect_args=connect_args, future=True)
    return create_engine(url, future=True)


def create_all(engine: Engine) -> None:
    """Create tables. Used for SQLite dev/tests; Postgres uses Alembic migrations."""
    Base.metadata.create_all(engine)


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)


def bootstrap(url: str | None = None) -> sessionmaker:
    """Convenience: build engine, create tables, return a session factory."""
    engine = make_engine(url)
    create_all(engine)
    return make_session_factory(engine)


_default_factory: sessionmaker | None = None


def default_session_factory() -> sessionmaker:
    """Process-wide session factory built from settings (SQLite unless DATABASE_URL set).

    For SQLite dev this also creates tables; Postgres deployments should run Alembic
    migrations instead, but create_all is harmless (only creates what's missing).
    """
    global _default_factory
    if _default_factory is None:
        _default_factory = bootstrap()
    return _default_factory
