"""Database engine / session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from rolegrep.config import DATA_DIR, DEFAULT_DATABASE_URL
from rolegrep.db.models import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None
_current_url: str | None = None


def database_url(url: str | None = None) -> str:
    return url or DEFAULT_DATABASE_URL


def get_engine(url: str | None = None, *, echo: bool = False) -> Engine:
    global _engine, _SessionLocal, _current_url
    resolved = database_url(url)

    if resolved.startswith("sqlite:///"):
        db_path = resolved.removeprefix("sqlite:///")
        if db_path not in {":memory:", ""} and not db_path.startswith("file:"):
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    if _engine is not None and _current_url == resolved:
        return _engine

    reset_engine()

    connect_args = {"check_same_thread": False} if resolved.startswith("sqlite") else {}
    _engine = create_engine(resolved, echo=echo, future=True, connect_args=connect_args)
    _current_url = resolved

    @event.listens_for(_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        if resolved.startswith("sqlite"):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    _SessionLocal = sessionmaker(
        bind=_engine, autoflush=False, autocommit=False, future=True
    )
    return _engine


def reset_engine() -> None:
    """Drop cached engine (tests / URL switches)."""
    global _engine, _SessionLocal, _current_url
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
    _current_url = None


def init_db(url: str | None = None) -> str:
    """Create tables. Returns the resolved database URL."""
    engine = get_engine(url)
    Base.metadata.create_all(bind=engine)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return database_url(url)


@contextmanager
def session_scope(url: str | None = None) -> Iterator[Session]:
    get_engine(url)
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
