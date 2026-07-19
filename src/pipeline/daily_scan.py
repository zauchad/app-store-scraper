"""Level 1 daily pipeline: scrape -> aggregate -> Opportunity Score.

Cheap and LLM-free, safe to run every day via GitHub Actions. Produces the
category heatmap the dashboard leads with, and returns the ranked list so the
deep-dive step knows which few niches deserve the expensive LLM pass.
"""
from __future__ import annotations

from typing import List

from src.analysis.opportunity import ScoredCategory, compute_and_store
from src.db.session import init_db
from src.logging_config import get_logger
from src.scraper.ingest import scrape_all

logger = get_logger(__name__)


def run_daily_scan(fetch_reviews: bool = True) -> List[ScoredCategory]:
    logger.info("=== Level 1 daily scan: START ===")
    init_db()
    counters = scrape_all(fetch_reviews=fetch_reviews)
    logger.info("Ingestion counters: %s", counters)
    scored = compute_and_store()
    top = scored[:5]
    logger.info(
        "Top niches: %s",
        ", ".join(f"{s.aggregate.name}={s.opportunity_score}" for s in top),
    )
    logger.info("=== Level 1 daily scan: DONE ===")
    return scored
