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
    DECLINE_MIN_DELTA,
    DECLINE_MIN_REVIEWS,
    FORTRESS_MIN_RATING,
    FORTRESS_MIN_REVIEWS,
    MEGA_MIN_REVIEWS,
    STALE_DAYS,
)
from src.db.models import App, AppSnapshot, Category
from src.logging_config import get_logger

logger = get_logger(__name__)

# Snapshots older than this (vs the newest one in the category) no longer
# describe the CURRENT competitive picture - the app fell off the chart.
SNAPSHOT_FRESH_DAYS = 7

# An app released within this window counts as a "newcomer" - the share of
# newcomers in the top measures whether the market still lets new players in.
NEWCOMER_MAX_AGE_DAYS = 2 * 365


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
    num_stale_incumbents: int  # sizeable apps not updated in 12m+ ("abandoned")
    median_days_since_update: Optional[int]
    raw_momentum: float  # signed avg review-count growth vs previous snapshot
    raw_rank_momentum: float  # avg rank improvement vs previous snapshot (up=+)
    num_developers: Optional[int] = None  # distinct publishers in the top
    top_dev_share: Optional[float] = None  # ratings share of biggest publisher
    english_only_share: Optional[float] = None  # sizeable apps shipping EN-only
    num_declining_incumbents: Optional[int] = None  # current version << lifetime
    monetization_score: Optional[float] = None  # free apps also in top-grossing
    paid_share: Optional[float] = None  # share of paid (price > 0) top apps
    newcomer_share: Optional[float] = None  # top apps released in last ~2 years


def _latest_snapshot_per_app(
    session: Session, genre_id: int, country: str = "us"
) -> List[AppSnapshot]:
    """Most recent snapshot for each app CURRENTLY charting in a category.

    Freshness window: apps that fell off the chart weeks ago keep their old
    snapshots, but they no longer describe today's competition - without the
    cutoff `num_apps` inflates forever and aggregates mix data from many dates.
    """
    cc = country.lower()
    newest = session.execute(
        select(func.max(AppSnapshot.captured_at)).where(
            AppSnapshot.genre_id == genre_id,
            AppSnapshot.country == cc,
        )
    ).scalar()
    if newest is None:
        return []
    cutoff = newest - timedelta(days=SNAPSHOT_FRESH_DAYS)
    subq = (
        select(
            AppSnapshot.app_id,
            func.max(AppSnapshot.captured_at).label("max_ts"),
        )
        .where(
            (AppSnapshot.genre_id == genre_id)
            & (AppSnapshot.country == cc)
            & (AppSnapshot.captured_at >= cutoff)
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
        .where(AppSnapshot.country == cc)
    )
    return list(session.execute(stmt).scalars().all())


def _previous_snapshot_map(
    session: Session, genre_id: int, before: datetime, country: str = "us"
) -> Dict[int, AppSnapshot]:
    """Latest snapshot per app strictly before `before` (for momentum)."""
    cc = country.lower()
    subq = (
        select(
            AppSnapshot.app_id,
            func.max(AppSnapshot.captured_at).label("max_ts"),
        )
        .where(
            (AppSnapshot.genre_id == genre_id)
            & (AppSnapshot.country == cc)
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
        .where(AppSnapshot.country == cc)
    )
    return {s.app_id: s for s in session.execute(stmt).scalars().all()}


def compute_category_aggregate(
    session: Session, genre_id: int, name: str, country: str = "us"
) -> Optional[CategoryAggregate]:
    latest = _latest_snapshot_per_app(session, genre_id, country=country)
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

    # Update cadence: how stale are the sizeable incumbents? (abandoned = opening)
    run_ts = max(s.captured_at for s in latest)
    stale_incumbents, median_days_update = _staleness(latest, run_ts)

    # Momentum: compare current review counts + rank to the previous run.
    prev = _previous_snapshot_map(
        session, genre_id, run_ts - timedelta(hours=1), country=country
    )
    momentum = _review_velocity(latest, prev)
    rank_momentum = _rank_velocity(latest, prev)

    num_devs, top_dev_share = _developer_concentration(session, latest)
    english_only = _english_only_share(session, latest)
    declining = _declining_incumbents(latest)
    monetization = _monetization_score(latest)
    paid_share, newcomer_share = _paid_and_newcomer_share(session, latest, run_ts)

    return CategoryAggregate(
        genre_id=genre_id,
        name=name,
        num_apps=len(latest),
        avg_rating_top=avg_rating,
        total_rating_count=total_counts,
        median_rating_count=median_counts,
        num_strong_incumbents=fortresses,
        num_mega_incumbents=megas,
        num_stale_incumbents=stale_incumbents,
        median_days_since_update=median_days_update,
        raw_momentum=momentum,
        raw_rank_momentum=rank_momentum,
        num_developers=num_devs,
        top_dev_share=top_dev_share,
        english_only_share=english_only,
        num_declining_incumbents=declining,
        monetization_score=monetization,
        paid_share=paid_share,
        newcomer_share=newcomer_share,
    )


def _monetization_score(latest: List[AppSnapshot]) -> Optional[float]:
    """Share of top-FREE apps that also rank in top-GROSSING.

    High = freemium converts here (users pay); low = attention without wallets.
    None until a scan has run with the grossing chart enabled.
    """
    free = [s for s in latest if s.in_free_chart]
    if not free or not any(s.in_grossing_chart for s in latest):
        return None
    both = sum(1 for s in free if s.in_grossing_chart)
    return round(both / len(free), 4)


def _paid_and_newcomer_share(
    session: Session, latest: List[AppSnapshot], run_ts: datetime
) -> tuple:
    """(share of paid apps in the top, share of apps released <2y ago)."""
    apps = _apps_for_snapshots(session, latest)
    if not apps:
        return None, None
    paid = sum(1 for a in apps if (a.price or 0) > 0)
    paid_share = round(paid / len(apps), 4)
    with_age = [a for a in apps if a.release_date is not None]
    newcomer_share = None
    if with_age:
        young = sum(
            1 for a in with_age
            if (run_ts - a.release_date).days <= NEWCOMER_MAX_AGE_DAYS
        )
        newcomer_share = round(young / len(with_age), 4)
    return paid_share, newcomer_share


def _apps_for_snapshots(session: Session, latest: List[AppSnapshot]) -> List[App]:
    ids = [s.app_id for s in latest]
    if not ids:
        return []
    return list(session.execute(select(App).where(App.id.in_(ids))).scalars())


def _developer_concentration(
    session: Session, latest: List[AppSnapshot]
) -> tuple:
    """(distinct publishers, ratings share of the biggest publisher).

    10 apps from 10 firms and 10 apps from 1 firm are radically different
    niches: a single publisher owning the top usually means a portfolio play
    that will out-ship any newcomer.
    """
    apps = _apps_for_snapshots(session, latest)
    if not apps:
        return None, None
    counts_by_app = {s.app_id: (s.rating_count or 0) for s in latest}
    by_dev: Dict[str, int] = {}
    for a in apps:
        key = str(a.artist_id) if a.artist_id else (a.developer or f"app-{a.id}")
        by_dev[key] = by_dev.get(key, 0) + counts_by_app.get(a.id, 0)
    total = sum(by_dev.values())
    top_share = round(max(by_dev.values()) / total, 4) if total > 0 else None
    return len(by_dev), top_share


def _english_only_share(
    session: Session, latest: List[AppSnapshot]
) -> Optional[float]:
    """Share of sizeable incumbents that ship in English only.

    High share = the audience exists but nobody serves other languages ->
    a localization opening (underserved user groups).
    """
    apps = _apps_for_snapshots(session, latest)
    counts_by_app = {s.app_id: (s.rating_count or 0) for s in latest}
    with_langs = [
        a for a in apps
        if a.language_codes and counts_by_app.get(a.id, 0) >= DECLINE_MIN_REVIEWS
    ]
    if not with_langs:
        return None
    en_only = sum(
        1 for a in with_langs
        if len(a.language_codes) == 1 and str(a.language_codes[0]).upper() == "EN"
    )
    return round(en_only / len(with_langs), 4)


def _declining_incumbents(latest: List[AppSnapshot]) -> Optional[int]:
    """Sizeable apps whose CURRENT version rates well below lifetime average."""
    have_signal = [
        s for s in latest
        if s.rating_avg is not None and s.rating_avg_current is not None
    ]
    if not have_signal:
        return None
    return sum(
        1 for s in have_signal
        if (s.rating_count or 0) >= DECLINE_MIN_REVIEWS
        and (s.rating_avg - s.rating_avg_current) >= DECLINE_MIN_DELTA
    )


def _staleness(latest: List[AppSnapshot], run_ts: datetime) -> tuple:
    """(num sizeable apps not updated in STALE_DAYS, median days-since-update)."""
    days_list: List[int] = []
    stale = 0
    for s in latest:
        upd = s.current_version_release_date
        if upd is None:
            continue
        days = (run_ts - upd).days
        days_list.append(days)
        if days > STALE_DAYS and (s.rating_count or 0) >= FORTRESS_MIN_REVIEWS:
            stale += 1
    median_days = int(statistics.median(days_list)) if days_list else None
    return stale, median_days


def _rank_velocity(
    latest: List[AppSnapshot], prev: Dict[int, AppSnapshot]
) -> float:
    """Avg rank improvement vs previous run (positive = apps climbing). 0 w/o history."""
    deltas: List[int] = []
    for s in latest:
        p = prev.get(s.app_id)
        if p is None or p.rank is None or s.rank is None:
            continue
        deltas.append(p.rank - s.rank)  # rank 5 -> 2 = +3 (improved)
    if not deltas:
        return 0.0
    return round(sum(deltas) / len(deltas), 4)


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


def compute_all_aggregates(session: Session, country: str = "us") -> List[CategoryAggregate]:
    cc = country.lower()
    cats = list(session.execute(select(Category).where(Category.enabled == True)).scalars())  # noqa: E712
    out: List[CategoryAggregate] = []
    for c in cats:
        agg = compute_category_aggregate(session, c.genre_id, c.name, country=cc)
        if agg:
            out.append(agg)
    logger.info("Computed aggregates for %d categories (%s)", len(out), cc)
    return out
