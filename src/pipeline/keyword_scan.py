"""Micro-niche pipeline: (optionally generate keywords) -> search -> score.

Two entry modes:
  * explicit terms  -> validate a list you already have in mind
  * generate=True    -> LLM proposes candidate niches for a theme/category first
"""
from __future__ import annotations

from typing import List, Optional

from src.analysis.keywords import generate_keywords
from src.analysis.microniche import KeywordResult, analyze_terms
from src.db.session import init_db
from src.logging_config import get_logger

logger = get_logger(__name__)


def run_keyword_scan(
    terms: Optional[List[str]] = None,
    theme: Optional[str] = None,
    genre_id: Optional[int] = None,
    generate: bool = False,
    n: int = 15,
) -> List[KeywordResult]:
    init_db()
    all_terms: List[str] = list(terms or [])
    source = "manual"

    if generate:
        seed_theme = theme or ""
        generated = generate_keywords(seed_theme, n=n, genre_id=genre_id)
        all_terms.extend(generated)
        source = "llm" if not terms else "mixed"

    all_terms = [t for t in dict.fromkeys(t.strip() for t in all_terms) if t]
    if not all_terms:
        logger.warning("No terms to analyse (provide --terms or --generate).")
        return []

    logger.info("=== Micro-niche scan: %d terms ===", len(all_terms))
    results = analyze_terms(all_terms, genre_id=genre_id, source=source)
    top = results[:5]
    logger.info(
        "Top micro-niches: %s",
        ", ".join(f"{r.term}={r.opportunity_score}" for r in top),
    )
    return results
