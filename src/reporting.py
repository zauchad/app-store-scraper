"""Read-side queries for the dashboard.

Keeps all SQL/ORM out of the Streamlit view so the UI stays declarative and the
queries are reusable/testable.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import select

from src.db.models import App, Category, CategoryInsight, CategoryScore
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
                "num_apps": score.num_apps,
                "avg_rating_top": score.avg_rating_top,
                "total_rating_count": score.total_rating_count,
                "strong_incumbents": score.num_strong_incumbents,
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
