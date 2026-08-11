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
    _widen_bigint_columns(engine)
    _backfill_country_column(engine)
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


def _widen_bigint_columns(engine: Engine) -> None:
    """Widen model BigInteger columns that still exist as 32-bit INTEGER.

    Needed because Apple track ids exceed 2^31-1. SQLite INTEGER is already
    64-bit, so this is a no-op there; Postgres needs an explicit ALTER.
    FKs that reference/widen those columns are dropped and recreated so
    Postgres type-matching checks pass.
    """
    from sqlalchemy import BigInteger

    if engine.dialect.name == "sqlite":
        return

    insp = inspect(engine)
    widen: list[tuple[str, str]] = []
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existing = {c["name"]: c for c in insp.get_columns(table.name)}
        for col in table.columns:
            if not isinstance(col.type, BigInteger):
                continue
            info = existing.get(col.name)
            if info is None:
                continue
            db_type = str(info["type"]).upper()
            if "BIGINT" in db_type or "INT8" in db_type:
                continue
            if "INT" not in db_type:
                continue
            widen.append((table.name, col.name))

    if not widen:
        return

    widen_set = set(widen)
    # (table, constraint_name, cols, referred_table, referred_cols)
    fks_to_restore: list[tuple[str, str, list[str], str, list[str]]] = []
    for table_name, _ in widen:
        if not insp.has_table(table_name):
            continue
        for fk in insp.get_foreign_keys(table_name):
            constrained = list(fk.get("constrained_columns") or [])
            referred = list(fk.get("referred_columns") or [])
            referred_table = fk.get("referred_table") or ""
            name = fk.get("name")
            if not name:
                continue
            touches = any((table_name, c) in widen_set for c in constrained) or any(
                (referred_table, r) in widen_set for r in referred
            )
            if touches:
                fks_to_restore.append(
                    (table_name, name, constrained, referred_table, referred)
                )

    # Also drop FKs on *other* tables that reference a widened PK (e.g. apps.id).
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        for fk in insp.get_foreign_keys(table.name):
            referred_table = fk.get("referred_table") or ""
            referred = list(fk.get("referred_columns") or [])
            name = fk.get("name")
            if not name:
                continue
            if any((referred_table, r) in widen_set for r in referred):
                entry = (
                    table.name,
                    name,
                    list(fk.get("constrained_columns") or []),
                    referred_table,
                    referred,
                )
                if entry not in fks_to_restore:
                    fks_to_restore.append(entry)

    try:
        with engine.begin() as conn:
            for table_name, name, *_ in fks_to_restore:
                conn.execute(
                    text(f'ALTER TABLE "{table_name}" DROP CONSTRAINT IF EXISTS "{name}"')
                )
            for table_name, col_name in widen:
                conn.execute(
                    text(
                        f'ALTER TABLE "{table_name}" '
                        f'ALTER COLUMN "{col_name}" TYPE BIGINT'
                    )
                )
                logger.info("Migrated: widened %s.%s to BIGINT", table_name, col_name)
            for table_name, name, cols, ref_table, ref_cols in fks_to_restore:
                col_list = ", ".join(f'"{c}"' for c in cols)
                ref_list = ", ".join(f'"{c}"' for c in ref_cols)
                conn.execute(
                    text(
                        f'ALTER TABLE "{table_name}" '
                        f'ADD CONSTRAINT "{name}" '
                        f"FOREIGN KEY ({col_list}) "
                        f'REFERENCES "{ref_table}" ({ref_list})'
                    )
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not widen INTEGER columns to BIGINT: %s", exc)


def _backfill_country_column(engine: Engine) -> None:
    """Legacy rows pre-date multi-storefront support; treat as US."""
    for table in ("app_snapshots", "category_scores"):
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(f"UPDATE {table} SET country = 'us' WHERE country IS NULL")
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not backfill %s.country: %s", table, exc)


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
