"""Windowed growth trends - the signal that only appears with weeks of history.

Day-over-day momentum is noisy (top charts barely move in a day, and multiple
scans/day can compare snapshots minutes apart -> ~0). REAL trend needs a window:
how much did engagement grow over the last N weeks?

We proxy engagement growth with rating-count growth (new ratings ≈ new usage) and
aggregate to the category via the MEDIAN app, so 1-2 giants can't dominate it.
Returns None where there isn't enough history yet (honest, not faked as 0).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import AppSnapshot, Category
from src.db.session import session_scope


@dataclass
class CategoryGrowth:
    genre_id: int
    name: str
    growth_pct: Optional[float]  # median per-app rating-count growth over window
    apps_with_history: int


def _snapshots_by_app(
    session: Session, genre_id: int, country: str = "us"
) -> Dict[int, List[AppSnapshot]]:
    cc = country.lower()
    rows = session.execute(
        select(AppSnapshot)
        .where(AppSnapshot.genre_id == genre_id)
        .where(AppSnapshot.country == cc)
        .order_by(AppSnapshot.app_id, AppSnapshot.captured_at.asc())
    ).scalars().all()
    by_app: Dict[int, List[AppSnapshot]] = {}
    for s in rows:
        by_app.setdefault(s.app_id, []).append(s)
    return by_app


def category_growth(
    session: Session, genre_id: int, name: str, weeks: int, country: str = "us"
) -> CategoryGrowth:
    by_app = _snapshots_by_app(session, genre_id, country=country)
    if not by_app:
        return CategoryGrowth(genre_id, name, None, 0)

    run_ts = max(s.captured_at for snaps in by_app.values() for s in snaps)
    cutoff = run_ts - timedelta(weeks=weeks)

    growths: List[float] = []
    for snaps in by_app.values():
        latest = snaps[-1]
        # latest snapshot at or before the cutoff = the "N weeks ago" baseline
        past = None
        for s in snaps:
            if s.captured_at <= cutoff:
                past = s
            else:
                break
        if past is None or not past.rating_count or latest.rating_count is None:
            continue
        growths.append((latest.rating_count - past.rating_count) / max(past.rating_count, 1))

    if not growths:
        return CategoryGrowth(genre_id, name, None, 0)
    return CategoryGrowth(genre_id, name, round(statistics.median(growths), 4), len(growths))


def all_category_growth(weeks: int = 4, country: str = "us") -> List[CategoryGrowth]:
    cc = country.lower()
    out: List[CategoryGrowth] = []
    with session_scope() as session:
        cats = session.execute(
            select(Category.genre_id, Category.name).where(Category.enabled == True)  # noqa: E712
        ).all()
        for genre_id, name in cats:
            out.append(category_growth(session, genre_id, name, weeks, country=cc))
    return out
