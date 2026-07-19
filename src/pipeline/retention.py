"""Snapshot retention / downsampling - keeps the DB roughly flat over time.

Policy (Alembic-free, DB-agnostic):
  * Keep EVERY snapshot from the last `retention_daily_days` (default 60) - the
    fine-grained window that powers day/week momentum & breakout detection.
  * For anything older, keep only ONE snapshot per app per ISO-week (the latest
    in that week) and delete the rest. Weekly resolution is plenty for long-range
    trend lines, at a fraction of the row count.

At ~1k snapshots/day this turns unbounded growth into a slow, bounded trickle,
so months (years) of history stay well within a free Postgres tier.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy import func, select

from src.config import settings
from src.db.models import AppSnapshot
from src.db.session import session_scope
from src.logging_config import get_logger

logger = get_logger(__name__)


def run_retention(daily_days: int | None = None) -> Dict[str, int]:
    days = daily_days if daily_days is not None else settings.retention_daily_days
    counters = {"scanned": 0, "kept_weekly": 0, "deleted": 0}

    with session_scope() as session:
        max_ts = session.execute(select(func.max(AppSnapshot.captured_at))).scalar()
        if max_ts is None:
            logger.info("Retention: no snapshots, nothing to do.")
            return counters
        cutoff = max_ts - timedelta(days=days)

        old = session.execute(
            select(
                AppSnapshot.id, AppSnapshot.app_id, AppSnapshot.captured_at
            )
            .where(AppSnapshot.captured_at < cutoff)
            .order_by(AppSnapshot.app_id, AppSnapshot.captured_at.asc())
        ).all()
        counters["scanned"] = len(old)
        if not old:
            logger.info("Retention: no snapshots older than %d days.", days)
            return counters

        # Per (app, ISO-year, ISO-week) keep the latest; delete the rest.
        keep_per_bucket: Dict[tuple, tuple] = {}  # bucket -> (id, captured_at)
        all_ids: Dict[int, tuple] = {}
        for sid, app_id, ts in old:
            iso = ts.isocalendar()
            bucket = (app_id, iso[0], iso[1])
            all_ids[sid] = bucket
            cur = keep_per_bucket.get(bucket)
            if cur is None or ts > cur[1]:
                keep_per_bucket[bucket] = (sid, ts)

        keep_ids = {v[0] for v in keep_per_bucket.values()}
        delete_ids = [sid for sid in all_ids if sid not in keep_ids]
        counters["kept_weekly"] = len(keep_ids)

        for batch in _chunks(delete_ids, 500):
            session.execute(
                AppSnapshot.__table__.delete().where(AppSnapshot.id.in_(batch))
            )
            counters["deleted"] += len(batch)

    logger.info("Retention done: %s", counters)
    return counters


def _chunks(items: List[int], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]
