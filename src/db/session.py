"""Engine / session management + schema bootstrap."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, inspect, text
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
    """Create tables and add any missing columns. Safe to call repeatedly.

    Lightweight, Alembic-free migration: after creating tables, we ADD COLUMN
    for any model column missing from an existing table. This keeps a long-lived
    DB (SQLite locally, Supabase in prod) in sync as the schema evolves, without
    forcing you to drop your data on every model change.
    """
    engine = get_engine()
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)
    logger.info("Schema ensured (%d tables)", len(Base.metadata.tables))


def _add_missing_columns(engine: Engine) -> None:
    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing:
                continue
            col_type = col.type.compile(dialect=engine.dialect)
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type}')
                    )
                logger.info("Migrated: added %s.%s", table.name, col.name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not add column %s.%s: %s", table.name, col.name, exc)


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
