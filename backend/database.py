"""Database helpers wired through the runtime kernel."""

from __future__ import annotations

from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker

from core.config import Settings


Base = declarative_base()

_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None


def configure_database(settings: Settings, *, echo: bool | None = None) -> None:
    """Create the SQLAlchemy engine/session factory using the provided settings."""

    global _engine, _session_factory
    _engine = create_engine(settings.DATABASE_URL, echo=echo)
    _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database engine not configured. Did you initialize the kernel?")
    return _engine


def get_session_factory() -> sessionmaker:
    if _session_factory is None:
        raise RuntimeError("Session factory not configured. Did you initialize the kernel?")
    return _session_factory


def get_db() -> Generator:
    """FastAPI dependency that yields a database session."""

    session = get_session_factory()
    db = session()
    try:
        yield db
    finally:
        db.close()
