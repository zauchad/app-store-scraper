"""Auto-discovery: drill from the top Level-1 categories down to micro-niches.

Closes the automation loop end to end:
  1. Take the most CONTESTABLE top categories from the latest Level-1 scan
     (skip giant-owned ones - no point drilling into Social Networking).
  2. For each, let the LLM propose candidate micro-niche keywords.
  3. Search + score each keyword, persist (source="auto").

Run daily after `scan` so the dashboard always shows fresh, winnable niches
without you typing anything.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select

from src.analysis.microniche import analyze_terms
from src.analysis.keywords import generate_keywords
from src.analysis.llm import is_quota_exhausted
from src.config import settings
from src.scraper.storefronts import PRIMARY_STOREFRONT
from src.db.models import Category, CategoryScore
from src.db.session import session_scope
from src.logging_config import get_logger

logger = get_logger(__name__)

# Don't waste LLM calls drilling into markets a lean founder can't enter.
MAX_MEGA_FOR_DRILL = 2


def _top_contestable_categories(
    top_k: int, country: str = PRIMARY_STOREFRONT
) -> List[tuple]:
    """Return [(genre_id, name)] of the best, still-contestable categories."""
    cc = country.lower()
    with session_scope() as session:
        rows = session.execute(
            select(
                CategoryScore.genre_id,
                CategoryScore.opportunity_score,
                CategoryScore.num_mega_incumbents,
                CategoryScore.computed_at,
                Category.name,
            )
            .join(Category, Category.genre_id == CategoryScore.genre_id)
            .where(CategoryScore.country == cc)
            .order_by(CategoryScore.computed_at.desc())
        ).all()

    seen = {}
    for genre_id, opp, mega, _ts, name in rows:
        if genre_id in seen:
            continue
        seen[genre_id] = (opp, mega or 0, name)

    ranked = sorted(seen.items(), key=lambda kv: kv[1][0], reverse=True)
    out = [
        (gid, meta[2])
        for gid, meta in ranked
        if meta[1] <= MAX_MEGA_FOR_DRILL
    ]
    return out[:top_k]


def run_discovery(
    top_k: Optional[int] = None, per_category: Optional[int] = None
) -> int:
    """Generate + score micro-niches for the top contestable categories."""
    if not settings.llm_enabled:
        logger.warning("Discovery needs an LLM (GEMINI_API_KEYS) to propose keywords.")
        return 0

    k = top_k if top_k is not None else settings.discover_top_categories
    n = per_category if per_category is not None else settings.discover_keywords_per_category
    targets = _top_contestable_categories(k)
    if not targets:
        logger.warning("No categories to drill (run `scan` first).")
        return 0

    logger.info("=== Auto-discovery on %d categories ===", len(targets))
    total = 0
    for genre_id, name in targets:
        if is_quota_exhausted():
            logger.warning("LLM daily quota exhausted - stopping discovery early.")
            break
        terms = generate_keywords(name, n=n, genre_id=genre_id)
        if not terms:
            continue
        results = analyze_terms(terms, genre_id=genre_id, source="auto")
        total += len(results)
        top = results[:3]
        logger.info(
            "  %s -> %s", name,
            ", ".join(f"{r.term}={r.opportunity_score}" for r in top),
        )
    logger.info("=== Auto-discovery DONE: %d micro-niches scored ===", total)
    return total
