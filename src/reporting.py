"""Read-side queries for the dashboard.

Keeps all SQL/ORM out of the Streamlit view so the UI stays declarative and the
queries are reusable/testable.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import select

from src.db.models import (
    App,
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
                "contestability": score.contestability,
                "num_apps": score.num_apps,
                "avg_rating_top": score.avg_rating_top,
                "total_rating_count": score.total_rating_count,
                "median_rating_count": score.median_rating_count,
                "strong_incumbents": score.num_strong_incumbents,
                "mega_incumbents": score.num_mega_incumbents,
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


def has_any_data() -> bool:
    with session_scope() as session:
        return session.query(CategoryScore).first() is not None


def latest_keyword_scores_df(limit: int = 200) -> pd.DataFrame:
    """Most recent score per keyword term (micro-niches), ranked."""
    with session_scope() as session:
        rows = session.execute(
            select(KeywordScore).order_by(KeywordScore.computed_at.desc()).limit(limit)
        ).scalars().all()

    seen = set()
    records: List[Dict] = []
    for s in rows:
        key = s.term.lower()
        if key in seen:
            continue
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
