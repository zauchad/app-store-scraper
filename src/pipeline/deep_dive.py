"""Level 2 pipeline: LLM synthesis for the top-K opportunity categories.

Runs only on the highest-scoring niches (cost control), turning their reviews
into Executive Summaries + pain points + suggested direction.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select

from src.analysis.insights import generate_insight_for_category
from src.analysis.llm import is_quota_exhausted
from src.analysis.opportunity import ScoredCategory
from src.config import settings
from src.scraper.storefronts import PRIMARY_STOREFRONT
from src.db.models import CategoryScore
from src.db.session import session_scope
from src.logging_config import get_logger

logger = get_logger(__name__)


def _top_genre_ids(top_k: int, country: str = PRIMARY_STOREFRONT) -> List[int]:
    """Genre IDs of the highest opportunity scores from the latest run."""
    cc = country.lower()
    with session_scope() as session:
        rows = session.execute(
            select(CategoryScore.genre_id, CategoryScore.opportunity_score)
            .where(CategoryScore.country == cc)
            .order_by(CategoryScore.computed_at.desc())
        ).all()
    # keep first (latest) occurrence per genre, then sort by score
    seen = {}
    for genre_id, score in rows:
        if genre_id not in seen:
            seen[genre_id] = score
    ranked = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)
    return [g for g, _ in ranked[:top_k]]


def run_deep_dive(
    top_k: Optional[int] = None, genre_ids: Optional[List[int]] = None
) -> int:
    """Generate LLM insights. Returns count of insights produced."""
    k = top_k if top_k is not None else settings.deep_dive_top_k
    targets = genre_ids if genre_ids else _top_genre_ids(k)
    logger.info("=== Level 2 deep dive on %d categories: %s ===", len(targets), targets)

    produced = 0
    for genre_id in targets:
        if is_quota_exhausted():
            logger.warning("LLM daily quota exhausted - stopping deep dive early.")
            break
        try:
            insight = generate_insight_for_category(genre_id)
            if insight is not None:
                produced += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("Deep dive failed for %s: %s", genre_id, exc)
    logger.info("=== Level 2 deep dive DONE: %d insights ===", produced)
    return produced
