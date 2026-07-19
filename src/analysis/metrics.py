"""Level 1 quantitative aggregates per category (no LLM, cheap, daily).

The whole point: turn a pile of snapshots into *business signals* that,
combined, distinguish a real opportunity from noise:

  1. DEMAND         - is there a healthy audience for a TYPICAL app here?
                      We use the MEDIAN review count, NOT the sum. Sum is
                      dominated by 1-2 giants (e.g. WhatsApp) and makes
                      giant-owned markets look "high demand" when they are
                      actually un-enterable. Median = the everyday player's
                      traction = real, contestable demand.
  2. QUALITY GAP    - are incumbents disappointing users? (low avg rating = gap)
  3. SATURATION     - how many entrenched "fortress" apps guard the niche?
  4. GIANTS (mega)  - how many un-beatable mega-incumbents own the space?
                      This is the guardrail that stops us recommending
                      "David vs 5 Goliaths" markets like Social Networking.
  5. MOMENTUM       - is the niche heating up? (review-count change vs prior)

Momentum needs history, so on day 1 it is dropped from the score (not faked as
neutral) and it sharpens each day the scan runs.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.analysis.scoring import (
    FORTRESS_MIN_RATING,
    FORTRESS_MIN_REVIEWS,
    MEGA_MIN_REVIEWS,
)
from src.db.models import AppSnapshot, Category
from src.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class CategoryAggregate:
    genre_id: int
    name: str
    num_apps: int
    avg_rating_top: Optional[float]
    total_rating_count: int
    median_rating_count: int
    num_strong_incumbents: int
    num_mega_incumbents: int
    raw_momentum: float  # signed avg review-count growth vs previous snapshot


def _latest_snapshot_per_app(
    session: Session, genre_id: int
) -> List[AppSnapshot]:
    """Most recent snapshot for each app in a category."""
    subq = (
        select(
            AppSnapshot.app_id,
            func.max(AppSnapshot.captured_at).label("max_ts"),
        )
        .where(AppSnapshot.genre_id == genre_id)
        .group_by(AppSnapshot.app_id)
        .subquery()
    )
    stmt = (
        select(AppSnapshot)
        .join(
            subq,
            (AppSnapshot.app_id == subq.c.app_id)
            & (AppSnapshot.captured_at == subq.c.max_ts),
        )
        .where(AppSnapshot.genre_id == genre_id)
    )
    return list(session.execute(stmt).scalars().all())


def _previous_snapshot_map(
    session: Session, genre_id: int, before: datetime
) -> Dict[int, AppSnapshot]:
    """Latest snapshot per app strictly before `before` (for momentum)."""
    subq = (
        select(
            AppSnapshot.app_id,
            func.max(AppSnapshot.captured_at).label("max_ts"),
        )
        .where(
            (AppSnapshot.genre_id == genre_id)
            & (AppSnapshot.captured_at < before)
        )
        .group_by(AppSnapshot.app_id)
        .subquery()
    )
    stmt = (
        select(AppSnapshot)
        .join(
            subq,
            (AppSnapshot.app_id == subq.c.app_id)
            & (AppSnapshot.captured_at == subq.c.max_ts),
        )
        .where(AppSnapshot.genre_id == genre_id)
    )
    return {s.app_id: s for s in session.execute(stmt).scalars().all()}


def compute_category_aggregate(
    session: Session, genre_id: int, name: str
) -> Optional[CategoryAggregate]:
    latest = _latest_snapshot_per_app(session, genre_id)
    if not latest:
        return None

    ratings = [s.rating_avg for s in latest if s.rating_avg is not None]
    counts = [s.rating_count or 0 for s in latest]
    avg_rating = round(sum(ratings) / len(ratings), 3) if ratings else None
    total_counts = int(sum(counts))
    median_counts = int(statistics.median(counts)) if counts else 0
    fortresses = sum(
        1
        for s in latest
        if (s.rating_avg or 0) >= FORTRESS_MIN_RATING
        and (s.rating_count or 0) >= FORTRESS_MIN_REVIEWS
    )
    megas = sum(1 for s in latest if (s.rating_count or 0) >= MEGA_MIN_REVIEWS)

    # Momentum: compare current review counts to the previous run.
    run_ts = max(s.captured_at for s in latest)
    prev = _previous_snapshot_map(session, genre_id, run_ts - timedelta(hours=1))
    momentum = _review_velocity(latest, prev)

    return CategoryAggregate(
        genre_id=genre_id,
        name=name,
        num_apps=len(latest),
        avg_rating_top=avg_rating,
        total_rating_count=total_counts,
        median_rating_count=median_counts,
        num_strong_incumbents=fortresses,
        num_mega_incumbents=megas,
        raw_momentum=momentum,
    )


def _review_velocity(
    latest: List[AppSnapshot], prev: Dict[int, AppSnapshot]
) -> float:
    """Avg % growth in review counts vs previous run. 0.0 when no history."""
    growths: List[float] = []
    for s in latest:
        p = prev.get(s.app_id)
        if p is None or not p.rating_count:
            continue
        cur = s.rating_count or 0
        growths.append((cur - p.rating_count) / max(p.rating_count, 1))
    if not growths:
        return 0.0
    return round(sum(growths) / len(growths), 5)


def compute_all_aggregates(session: Session) -> List[CategoryAggregate]:
    cats = list(session.execute(select(Category).where(Category.enabled == True)).scalars())  # noqa: E712
    out: List[CategoryAggregate] = []
    for c in cats:
        agg = compute_category_aggregate(session, c.genre_id, c.name)
        if agg:
            out.append(agg)
    logger.info("Computed aggregates for %d categories", len(out))
    return out
