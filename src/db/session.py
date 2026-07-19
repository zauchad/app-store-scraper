"""Engine / session management + schema bootstrap."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import settings
from src.db.models import Base
from src.logging_config import get_logger

logger = get_logger(__name__)

_engine: Engine | None = None
_SessionFactory: sessionmaker | None = None


def _ensure_sqlite_parent_dir(url: str) -> None:
    """Create the parent folder for a file-based SQLite DB if it's missing."""
    from pathlib import Path

    prefix = "sqlite:///"
    if url.startswith(prefix):
        path = url[len(prefix):]
        if path and path != ":memory:":
            Path(path).resolve().parent.mkdir(parents=True, exist_ok=True)


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = settings.resolved_database_url
        connect_args = {}
        if url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
            _ensure_sqlite_parent_dir(url)
        _engine = create_engine(
            url, pool_pre_ping=True, future=True, connect_args=connect_args
        )
        logger.info("DB engine created (%s)", url.split("@")[-1])
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(
            bind=get_engine(), autoflush=False, expire_on_commit=False, future=True
        )
    return _SessionFactory


def init_db() -> None:
    """Create all tables if they don't exist. Safe to call repeatedly."""
    Base.metadata.create_all(get_engine())
    logger.info("Schema ensured (%d tables)", len(Base.metadata.tables))


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session with commit/rollback handling."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
