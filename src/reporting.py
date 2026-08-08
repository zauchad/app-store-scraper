"""Read-side queries for the dashboard.

Keeps all SQL/ORM out of the Streamlit view so the UI stays declarative and the
queries are reusable/testable.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import select

from src.db.models import (
    App,
    AppSnapshot,
    Category,
    CategoryInsight,
    CategoryScore,
    KeywordScore,
)
from src.db.session import session_scope


def latest_scores_df() -> pd.DataFrame:
    """One row per category = its most recent Opportunity Score + marketing math."""
    with session_scope() as session:
        rows = session.execute(
            select(CategoryScore, Category.name)
            .join(Category, Category.genre_id == CategoryScore.genre_id)
            .order_by(CategoryScore.computed_at.desc())
        ).all()

    seen = set()
    records: List[Dict] = []
    for score, name in rows:
        if score.genre_id in seen:
            continue
        seen.add(score.genre_id)
        records.append(
            {
                "genre_id": score.genre_id,
                "category": name,
                "opportunity_score": score.opportunity_score,
                "demand": score.demand_score,
                "quality_gap": score.quality_gap_score,
                "low_saturation": score.low_saturation_score,
                "momentum": score.momentum_score,
                "rank_momentum": score.rank_momentum,
                "contestability": score.contestability,
                "num_apps": score.num_apps,
                "avg_rating_top": score.avg_rating_top,
                "total_rating_count": score.total_rating_count,
                "median_rating_count": score.median_rating_count,
                "strong_incumbents": score.num_strong_incumbents,
                "mega_incumbents": score.num_mega_incumbents,
                "stale_incumbents": score.num_stale_incumbents,
                "median_days_since_update": score.median_days_since_update,
                "num_developers": score.num_developers,
                "top_dev_share": score.top_dev_share,
                "english_only_share": score.english_only_share,
                "declining_incumbents": score.num_declining_incumbents,
                "est_cpi_pln": score.est_cpi_pln,
                "est_installs_month": score.est_installs_month,
                "marketing_cost_pln": score.marketing_cost_pln,
                "success_probability": score.success_probability,
                "computed_at": score.computed_at,
            }
        )
    df = pd.DataFrame(records)
    if not df.empty:
        df = df.sort_values("opportunity_score", ascending=False).reset_index(drop=True)
    return df


def latest_insight(genre_id: int) -> Optional[CategoryInsight]:
    with session_scope() as session:
        return session.execute(
            select(CategoryInsight)
            .where(CategoryInsight.genre_id == genre_id)
            .order_by(CategoryInsight.generated_at.desc())
            .limit(1)
        ).scalars().first()


def top_apps_for_category(genre_id: int, limit: int = 15) -> pd.DataFrame:
    with session_scope() as session:
        apps = session.execute(
            select(App).where(App.genre_id == genre_id).limit(200)
        ).scalars().all()
        records = [
            {
                "name": a.name,
                "developer": a.developer,
                "price": a.price,
                "url": a.url,
            }
            for a in apps
        ]
    df = pd.DataFrame(records)
    return df.head(limit)


def competitors_for_category(genre_id: int, limit: int = 40) -> pd.DataFrame:
    """Rich competitor list for a category: latest rating/count + url + staleness.

    Feeds both the "competitors" table (with clickable App Store links) and the
    clone-and-improve candidate ranking. Uses each app's most recent snapshot for
    rating/count and its stored update cadence for days-since-update.
    """
    now = datetime.utcnow()
    with session_scope() as session:
        apps = session.execute(
            select(App).where(App.genre_id == genre_id).limit(300)
        ).scalars().all()
        app_by_id = {a.id: a for a in apps}

        # One query for all snapshots of these apps; keep the latest per app.
        latest: Dict[int, tuple] = {}
        if app_by_id:
            snaps = session.execute(
                select(
                    AppSnapshot.app_id,
                    AppSnapshot.rating_avg,
                    AppSnapshot.rating_count,
                )
                .where(AppSnapshot.app_id.in_(list(app_by_id)))
                .order_by(AppSnapshot.app_id, AppSnapshot.captured_at.desc())
            ).all()
            for s in snaps:
                if s.app_id not in latest:  # first seen = newest (desc order)
                    latest[s.app_id] = (s.rating_avg, s.rating_count)

        records: List[Dict] = []
        for a in apps:
            rating, ratings = latest.get(a.id, (None, None))
            days = None
            if a.current_version_release_date is not None:
                days = (now - a.current_version_release_date).days
            records.append(
                {
                    "app_id": a.id,
                    "name": a.name,
                    "developer": a.developer,
                    "rating": rating,
                    "ratings": int(ratings) if ratings else 0,
                    "price": a.price,
                    "url": a.url or (f"https://apps.apple.com/app/id{a.id}"),
                    "days_since_update": days,
                }
            )
    df = pd.DataFrame(records)
    if not df.empty:
        df = df.sort_values("ratings", ascending=False).reset_index(drop=True)
    return df.head(limit)


def has_any_data() -> bool:
    with session_scope() as session:
        return session.query(CategoryScore).first() is not None


def category_growth_df(weeks: int = 4) -> pd.DataFrame:
    """Median per-app engagement growth over the last N weeks, per category."""
    from src.analysis.trends import all_category_growth

    rows = all_category_growth(weeks=weeks)
    df = pd.DataFrame(
        [
            {
                "genre_id": r.genre_id,
                "category": r.name,
                "growth_pct": r.growth_pct,
                "apps_with_history": r.apps_with_history,
            }
            for r in rows
        ]
    )
    return df


def category_rating_history(genre_id: int, limit: int = 60) -> pd.DataFrame:
    """Time series of the category's avg incumbent rating (quality over time).

    Falling line = incumbents getting worse = a FRESH quality gap opening up.
    Built straight from stored CategoryScore rows - no extra data needed.
    """
    with session_scope() as session:
        rows = session.execute(
            select(CategoryScore.computed_at, CategoryScore.avg_rating_top)
            .where(CategoryScore.genre_id == genre_id)
            .order_by(CategoryScore.computed_at.asc())
            .limit(limit)
        ).all()
    df = pd.DataFrame(
        [{"date": r[0], "avg_rating": r[1]} for r in rows if r[1] is not None]
    )
    return df


def quality_movers_df(limit: int = 15, min_drop: float = 0.05) -> pd.DataFrame:
    """Apps whose rating DROPPED most vs the prior run (fresh openings).

    A sizeable app whose rating is sliding = users turning sour = an opening for
    a better product. Needs >=2 runs of history.
    """
    from src.db.models import AppSnapshot

    with session_scope() as session:
        snaps = session.execute(
            select(
                AppSnapshot.app_id,
                AppSnapshot.rating_avg,
                AppSnapshot.rating_count,
                AppSnapshot.captured_at,
                App.name,
                App.developer,
                Category.name.label("category"),
            )
            .join(App, App.id == AppSnapshot.app_id)
            .join(Category, Category.genre_id == AppSnapshot.genre_id, isouter=True)
            .order_by(AppSnapshot.app_id, AppSnapshot.captured_at.desc())
        ).all()

    per_app: Dict[int, list] = {}
    for row in snaps:
        per_app.setdefault(row.app_id, [])
        if len(per_app[row.app_id]) < 2:
            per_app[row.app_id].append(row)

    records: List[Dict] = []
    for rows in per_app.values():
        if len(rows) < 2:
            continue
        cur, prev = rows[0], rows[1]
        if cur.rating_avg is None or prev.rating_avg is None:
            continue
        drop = round(prev.rating_avg - cur.rating_avg, 3)
        if drop < min_drop:
            continue
        records.append(
            {
                "name": cur.name,
                "developer": cur.developer,
                "category": cur.category,
                "rating_now": round(cur.rating_avg, 2),
                "rating_prev": round(prev.rating_avg, 2),
                "rating_drop": drop,
                "rating_count": cur.rating_count,
            }
        )
    df = pd.DataFrame(records)
    if not df.empty:
        df = df.sort_values("rating_drop", ascending=False).reset_index(drop=True)
    return df.head(limit)


def rising_apps_df(limit: int = 25, min_improvement: int = 1) -> pd.DataFrame:
    """Breakout detection: apps whose chart rank improved most vs the prior run.

    Compares each app's two most recent snapshots (needs >=2 runs of history).
    Positive `rank_delta` = climbing (e.g. #40 -> #12 = +28). This is the
    free equivalent of data.ai's 'Rising / Breakout' list.
    """
    from src.db.models import AppSnapshot

    with session_scope() as session:
        snaps = session.execute(
            select(
                AppSnapshot.app_id,
                AppSnapshot.genre_id,
                AppSnapshot.rank,
                AppSnapshot.rating_count,
                AppSnapshot.captured_at,
                App.name,
                App.developer,
                Category.name.label("category"),
            )
            .join(App, App.id == AppSnapshot.app_id)
            .join(Category, Category.genre_id == AppSnapshot.genre_id, isouter=True)
            .order_by(AppSnapshot.app_id, AppSnapshot.captured_at.desc())
        ).all()

    # Keep the two latest snapshots per app.
    per_app: Dict[int, list] = {}
    for row in snaps:
        per_app.setdefault(row.app_id, [])
        if len(per_app[row.app_id]) < 2:
            per_app[row.app_id].append(row)

    records: List[Dict] = []
    for rows in per_app.values():
        if len(rows) < 2:
            continue
        cur, prev = rows[0], rows[1]
        if cur.rank is None or prev.rank is None:
            continue
        delta = prev.rank - cur.rank
        if delta < min_improvement:
            continue
        records.append(
            {
                "name": cur.name,
                "developer": cur.developer,
                "category": cur.category,
                "rank_now": cur.rank,
                "rank_prev": prev.rank,
                "rank_delta": delta,
                "rating_count": cur.rating_count,
            }
        )
    df = pd.DataFrame(records)
    if not df.empty:
        df = df.sort_values("rank_delta", ascending=False).reset_index(drop=True)
    return df.head(limit)


def latest_keyword_scores_df(limit: int = 200) -> pd.DataFrame:
    """Most recent score per keyword term (micro-niches), ranked.

    Deduplicated BEFORE limiting, so re-analysing recent terms never pushes
    older micro-niches out of the dashboard.
    """
    with session_scope() as session:
        rows = session.execute(
            select(KeywordScore).order_by(KeywordScore.computed_at.desc())
        ).scalars().all()

    seen = set()
    records: List[Dict] = []
    for s in rows:
        key = s.term.lower()
        if key in seen:
            continue
        if len(records) >= limit:
            break
        seen.add(key)
        records.append(
            {
                "term": s.term,
                "genre_id": s.genre_id,
                "opportunity_score": s.opportunity_score,
                "success_probability": s.success_probability,
                "demand": s.demand_score,
                "quality_gap": s.quality_gap_score,
                "low_saturation": s.low_saturation_score,
                "contestability": s.contestability,
                "search_interest": s.search_interest,
                "difficulty": s.difficulty,
                "avg_rating_top": s.avg_rating_top,
                "median_rating_count": s.median_rating_count,
                "strong_incumbents": s.num_strong_incumbents,
                "mega_incumbents": s.num_mega_incumbents,
                "num_results": s.num_results,
                "est_cpi_pln": s.est_cpi_pln,
                "est_installs_month": s.est_installs_month,
                "marketing_cost_pln": s.marketing_cost_pln,
                "top_apps": s.top_apps,
                "computed_at": s.computed_at,
            }
        )
    df = pd.DataFrame(records)
    if not df.empty:
        df = df.sort_values("opportunity_score", ascending=False).reset_index(drop=True)
    return df


def pain_mining_for_category(genre_id: int):
    """LLM-free pain themes / phrases / most-hated apps for a category."""
    from src.analysis.review_mining import mine_pains

    return mine_pains(genre_id=genre_id)


def pain_mining_for_apps(app_ids: List[int]):
    """Same mining, scoped to an explicit competitor list (micro-niche)."""
    from src.analysis.review_mining import mine_pains

    return mine_pains(app_ids=app_ids)


def developer_concentration_df(genre_id: int, limit: int = 10) -> pd.DataFrame:
    """Who owns the niche: publishers ranked by their share of all ratings."""
    from src.analysis.metrics import _latest_snapshot_per_app

    with session_scope() as session:
        latest = _latest_snapshot_per_app(session, genre_id)
        ids = [s.app_id for s in latest]
        apps = (
            session.execute(select(App).where(App.id.in_(ids))).scalars().all()
            if ids else []
        )
    counts = {s.app_id: (s.rating_count or 0) for s in latest}
    by_dev: Dict[str, Dict] = {}
    for a in apps:
        key = a.developer or f"app-{a.id}"
        d = by_dev.setdefault(key, {"developer": key, "apps": 0, "ratings": 0})
        d["apps"] += 1
        d["ratings"] += counts.get(a.id, 0)
    total = sum(d["ratings"] for d in by_dev.values()) or 1
    records = [
        {**d, "share": round(d["ratings"] / total, 4)} for d in by_dev.values()
    ]
    df = pd.DataFrame(records)
    if not df.empty:
        df = df.sort_values("ratings", ascending=False).reset_index(drop=True)
    return df.head(limit)


def declining_apps_df(genre_id: Optional[int] = None, limit: int = 15) -> pd.DataFrame:
    """Apps whose CURRENT version rates well below their lifetime average.

    The freshest free "users are souring right now" signal - visible after the
    first scan that captures `averageUserRatingForCurrentVersion`.
    """
    from src.analysis.scoring import DECLINE_MIN_DELTA

    with session_scope() as session:
        stmt = (
            select(
                AppSnapshot.app_id,
                AppSnapshot.rating_avg,
                AppSnapshot.rating_avg_current,
                AppSnapshot.rating_count,
                AppSnapshot.captured_at,
                App.name,
                App.developer,
                Category.name.label("category"),
            )
            .join(App, App.id == AppSnapshot.app_id)
            .join(Category, Category.genre_id == AppSnapshot.genre_id, isouter=True)
            .where(AppSnapshot.rating_avg_current.isnot(None))
            .order_by(AppSnapshot.app_id, AppSnapshot.captured_at.desc())
        )
        if genre_id is not None:
            stmt = stmt.where(AppSnapshot.genre_id == genre_id)
        snaps = session.execute(stmt).all()

    seen = set()
    records: List[Dict] = []
    for row in snaps:
        if row.app_id in seen:
            continue
        seen.add(row.app_id)
        if row.rating_avg is None or row.rating_avg_current is None:
            continue
        delta = round(row.rating_avg - row.rating_avg_current, 2)
        if delta < DECLINE_MIN_DELTA:
            continue
        records.append(
            {
                "name": row.name,
                "developer": row.developer,
                "category": row.category,
                "rating_lifetime": round(row.rating_avg, 2),
                "rating_current_version": round(row.rating_avg_current, 2),
                "delta": delta,
                "rating_count": row.rating_count,
            }
        )
    df = pd.DataFrame(records)
    if not df.empty:
        df = df.sort_values("delta", ascending=False).reset_index(drop=True)
    return df.head(limit)


def localization_gap_df(genre_id: int, limit: int = 20) -> pd.DataFrame:
    """Sizeable incumbents and the languages they ship - EN-only = opening."""
    from src.analysis.metrics import _latest_snapshot_per_app

    with session_scope() as session:
        latest = _latest_snapshot_per_app(session, genre_id)
        ids = [s.app_id for s in latest]
        apps = (
            session.execute(select(App).where(App.id.in_(ids))).scalars().all()
            if ids else []
        )
    counts = {s.app_id: (s.rating_count or 0) for s in latest}
    records: List[Dict] = []
    for a in apps:
        if not a.language_codes:
            continue
        langs = [str(c).upper() for c in a.language_codes]
        records.append(
            {
                "name": a.name,
                "developer": a.developer,
                "ratings": counts.get(a.id, 0),
                "num_languages": len(langs),
                "english_only": langs == ["EN"],
                "languages": ", ".join(langs[:12]) + ("…" if len(langs) > 12 else ""),
            }
        )
    df = pd.DataFrame(records)
    if not df.empty:
        df = df.sort_values("ratings", ascending=False).reset_index(drop=True)
    return df.head(limit)


def recent_release_notes_df(genre_id: int, limit: int = 10) -> pd.DataFrame:
    """What the competition shipped most recently (feature velocity radar)."""
    with session_scope() as session:
        apps = session.execute(
            select(App)
            .where(
                (App.genre_id == genre_id)
                & (App.release_notes.isnot(None))
                & (App.current_version_release_date.isnot(None))
            )
            .order_by(App.current_version_release_date.desc())
            .limit(limit)
        ).scalars().all()
        records = [
            {
                "name": a.name,
                "developer": a.developer,
                "updated": a.current_version_release_date,
                "release_notes": (a.release_notes or "")[:500],
            }
            for a in apps
        ]
    return pd.DataFrame(records)
