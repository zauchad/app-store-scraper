"""Micro-niche (keyword) scoring - the "below the top charts" layer.

For a candidate search term we pull the apps that actually rank for it (via the
free Search API) and score the niche with the SAME model as categories:

    Opportunity = attractiveness x contestability

Key difference vs categories: demand here is ABSOLUTE (not relative to a full
category set), because keywords are analysed ad-hoc / in small batches. A niche
whose typical ranking app has ~200k ratings reads as strong demand on its own,
without needing 20 other keywords to compare against.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import List, Optional

from src.analysis.marketing import MarketingEstimate, estimate
from src.analysis.scoring import (
    absolute_quality_gap,
    contestability,
    count_incumbents,
    effective_weights,
    keyword_difficulty,
)
from src.config import settings
from src.db.models import Keyword, KeywordScore
from src.db.session import session_scope
from src.logging_config import get_logger
from src.scraper.categories import CATEGORY_SEEDS
from src.scraper.itunes_client import AppMetadata, ItunesClient
from src.scraper.search_volume import get_volume_provider

logger = get_logger(__name__)

# A keyword whose typical ranking app has this many ratings = strong demand.
DEMAND_REF = 200_000
# Saturation reference: this many fortresses = fully saturated.
SATURATION_REF = 12
# Only the top results define the niche's competitive reality.
TOP_N_RESULTS = 20


@dataclass
class KeywordResult:
    term: str
    genre_id: Optional[int]
    num_results: int
    avg_rating_top: Optional[float]
    median_rating_count: int
    total_rating_count: int
    num_strong_incumbents: int
    num_mega_incumbents: int
    demand_score: float
    quality_gap_score: float
    low_saturation_score: float
    contestability: float
    search_interest: Optional[float]
    difficulty: float
    opportunity_score: float
    marketing: MarketingEstimate
    top_apps: List[dict]


def _cpi_for_genre(genre_id: Optional[int]) -> float:
    if genre_id is not None:
        for seed in CATEGORY_SEEDS:
            if seed.genre_id == genre_id:
                return seed.base_cpi_usd
    return 3.0


def score_keyword(
    term: str,
    apps: List[AppMetadata],
    genre_id: Optional[int] = None,
    search_interest: Optional[float] = None,
) -> Optional[KeywordResult]:
    if not apps:
        return None

    top = apps[:TOP_N_RESULTS]
    rows = [(a.rating_avg, a.rating_count or 0) for a in top]
    ratings = [a.rating_avg for a in top if a.rating_avg is not None]
    counts = [a.rating_count or 0 for a in top]

    avg_rating = round(sum(ratings) / len(ratings), 3) if ratings else None
    median_count = int(statistics.median(counts)) if counts else 0
    total_count = int(sum(counts))
    num_fortress, num_mega = count_incumbents(rows)

    # DEMAND = blend of app engagement (median ratings) and search interest.
    engagement = min(math.log1p(median_count) / math.log1p(DEMAND_REF), 1.0)
    if search_interest is None:
        demand = engagement
    else:
        w = settings.demand_search_weight
        demand = (1.0 - w) * engagement + w * search_interest
    quality_gap = absolute_quality_gap(avg_rating)
    low_saturation = max(0.0, 1.0 - num_fortress / SATURATION_REF)
    difficulty = keyword_difficulty(median_count, num_fortress, num_mega, len(top))

    weights = effective_weights(has_momentum=False)
    attractiveness = (
        weights["demand"] * demand
        + weights["quality_gap"] * quality_gap
        + weights["low_saturation"] * low_saturation
    )
    contest = contestability(num_mega, num_fortress)
    opp = round(100.0 * attractiveness * contest, 2)

    mkt = estimate(
        base_cpi_usd=_cpi_for_genre(genre_id),
        opportunity_0_100=opp,
        quality_gap_0_1=quality_gap,
        contestability=contest,
        total_rating_count=total_count,
        num_apps=len(top),
    )

    top_apps = [
        {
            "name": a.name,
            "developer": a.developer,
            "rating": a.rating_avg,
            "ratings": a.rating_count or 0,
        }
        for a in top[:10]
    ]

    return KeywordResult(
        term=term,
        genre_id=genre_id,
        num_results=len(apps),
        avg_rating_top=avg_rating,
        median_rating_count=median_count,
        total_rating_count=total_count,
        num_strong_incumbents=num_fortress,
        num_mega_incumbents=num_mega,
        demand_score=round(demand, 4),
        quality_gap_score=round(quality_gap, 4),
        low_saturation_score=round(low_saturation, 4),
        contestability=round(contest, 4),
        search_interest=round(search_interest, 4) if search_interest is not None else None,
        difficulty=round(difficulty, 4),
        opportunity_score=opp,
        marketing=mkt,
        top_apps=top_apps,
    )


def analyze_terms(
    terms: List[str], genre_id: Optional[int] = None, source: str = "manual"
) -> List[KeywordResult]:
    """Search + score a batch of candidate micro-niches, persist, return ranked."""
    client = ItunesClient(country=settings.store_country)
    volume = get_volume_provider()
    results: List[KeywordResult] = []
    for term in terms:
        term = term.strip()
        if not term:
            continue
        apps = client.search(term, limit=50)
        interest = volume.interest(term)
        res = score_keyword(term, apps, genre_id, search_interest=interest)
        if res is not None:
            results.append(res)

    _persist(results, source)
    results.sort(key=lambda r: r.opportunity_score, reverse=True)
    logger.info("Analysed %d micro-niches", len(results))
    return results


def _persist(results: List[KeywordResult], source: str) -> None:
    with session_scope() as session:
        for r in results:
            kw = Keyword(term=r.term, genre_id=r.genre_id, source=source)
            session.add(kw)
            session.flush()
            session.add(
                KeywordScore(
                    keyword_id=kw.id,
                    term=r.term,
                    genre_id=r.genre_id,
                    num_results=r.num_results,
                    avg_rating_top=r.avg_rating_top,
                    median_rating_count=r.median_rating_count,
                    total_rating_count=r.total_rating_count,
                    num_strong_incumbents=r.num_strong_incumbents,
                    num_mega_incumbents=r.num_mega_incumbents,
                    demand_score=r.demand_score,
                    quality_gap_score=r.quality_gap_score,
                    low_saturation_score=r.low_saturation_score,
                    contestability=r.contestability,
                    search_interest=r.search_interest,
                    difficulty=r.difficulty,
                    opportunity_score=r.opportunity_score,
                    est_cpi_pln=r.marketing.est_cpi_pln,
                    est_installs_month=r.marketing.est_installs_month,
                    marketing_cost_pln=r.marketing.marketing_cost_pln,
                    success_probability=r.marketing.success_probability,
                    top_apps=r.top_apps,
                )
            )
