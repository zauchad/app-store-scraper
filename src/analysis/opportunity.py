"""Opportunity Score = the headline business conclusion of Level 1.

Design (v2 - fixes the "Social Networking looks great" fallacy):

    attractiveness = w_demand * demand          (median-based, giant-robust)
                   + w_gap    * quality_gap      (ABSOLUTE gap vs a 4.6 bar)
                   + w_sat    * low_saturation   (fewer fortresses = better)
                   + w_mom    * momentum         (dropped on day 1, not faked)

    contestability = can a LEAN founder even play here?
                   = mega_penalty * fortress_penalty   (0..1 multiplier)

    Opportunity = 100 * attractiveness * contestability

Why the multiplier and not just another weighted term: a market owned by giants
(WhatsApp, Facebook, WeChat...) is not "a bit less attractive" - it is
structurally un-enterable on 7.5k PLN/month. The multiplier collapses such
markets toward 0, which is the honest business answer.

Two big changes vs v1:
  * DEMAND uses the MEDIAN review count (log-scaled), so 1-2 mega apps can't
    make a giant-owned category look like high, winnable demand.
  * QUALITY GAP is ABSOLUTE (how far incumbents sit below a 4.6 bar), so a
    well-loved 4.37 market correctly reads as a SMALL gap, not a big one just
    because other categories happen to rate higher.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List

from src.analysis.marketing import MarketingEstimate, estimate
from src.analysis.metrics import CategoryAggregate, compute_all_aggregates
from src.analysis.scoring import (
    absolute_quality_gap,
    contestability,
    effective_weights,
)
from src.config import settings
from src.db.models import Category, CategoryScore
from src.db.session import session_scope
from src.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ScoredCategory:
    aggregate: CategoryAggregate
    demand_score: float
    quality_gap_score: float
    low_saturation_score: float
    momentum_score: float
    rank_momentum: float
    contestability: float
    opportunity_score: float
    marketing: MarketingEstimate


def _minmax(values: List[float]) -> Dict[int, float]:
    """Return index -> normalised 0..1. Flat input -> all 0.0 (no signal)."""
    if not values:
        return {}
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return {i: 0.0 for i in range(len(values))}
    return {i: (v - lo) / (hi - lo) for i, v in enumerate(values)}


def score_categories(aggregates: List[CategoryAggregate]) -> List[ScoredCategory]:
    if not aggregates:
        return []

    # DEMAND: log-scaled median review count, normalised across categories.
    demand_raw = [math.log1p(max(a.median_rating_count, 0)) for a in aggregates]
    # SATURATION: number of fortresses, normalised.
    sat_raw = [float(a.num_strong_incumbents) for a in aggregates]
    # MOMENTUM: heating-up signal from BOTH review velocity and rank climbing.
    mom_raw = [a.raw_momentum for a in aggregates]
    rank_raw = [a.raw_rank_momentum for a in aggregates]

    demand_n = _minmax(demand_raw)
    sat_n = _minmax(sat_raw)
    mom_n = _minmax(mom_raw)
    rank_n = _minmax(rank_raw)

    has_review_mom = any(abs(m) > 1e-9 for m in mom_raw)
    has_rank_mom = any(abs(m) > 1e-9 for m in rank_raw)
    has_momentum = has_review_mom or has_rank_mom
    weights = effective_weights(has_momentum)

    cpi_by_genre = _cpi_lookup()

    scored: List[ScoredCategory] = []
    for i, agg in enumerate(aggregates):
        demand = demand_n[i]
        quality_gap = absolute_quality_gap(agg.avg_rating_top)
        low_saturation = 1.0 - sat_n[i]
        # Blend the two momentum sources where each has history.
        if has_review_mom and has_rank_mom:
            momentum = 0.5 * mom_n[i] + 0.5 * rank_n[i]
        elif has_review_mom:
            momentum = mom_n[i]
        elif has_rank_mom:
            momentum = rank_n[i]
        else:
            momentum = 0.0

        attractiveness = (
            weights["demand"] * demand
            + weights["quality_gap"] * quality_gap
            + weights["low_saturation"] * low_saturation
            + weights["momentum"] * momentum
        )
        contest = contestability(
            agg.num_mega_incumbents, agg.num_strong_incumbents
        )
        opp = round(100.0 * attractiveness * contest, 2)

        mkt = estimate(
            base_cpi_usd=cpi_by_genre.get(agg.genre_id, 3.0),
            opportunity_0_100=opp,
            quality_gap_0_1=quality_gap,
            contestability=contest,
            total_rating_count=agg.total_rating_count,
            num_apps=agg.num_apps,
        )

        scored.append(
            ScoredCategory(
                aggregate=agg,
                demand_score=round(demand, 4),
                quality_gap_score=round(quality_gap, 4),
                low_saturation_score=round(low_saturation, 4),
                momentum_score=round(momentum, 4),
                rank_momentum=round(agg.raw_rank_momentum, 4),
                contestability=round(contest, 4),
                opportunity_score=opp,
                marketing=mkt,
            )
        )

    scored.sort(key=lambda s: s.opportunity_score, reverse=True)
    return scored


def _cpi_lookup() -> Dict[int, float]:
    with session_scope() as session:
        rows = session.query(Category).all()
        return {c.genre_id: c.base_cpi_usd for c in rows}


def compute_and_store(country: str | None = None) -> List[ScoredCategory]:
    """Compute aggregates, score, and persist a CategoryScore row per category."""
    cc = (country or settings.store_country).lower()
    with session_scope() as session:
        aggregates = compute_all_aggregates(session, country=cc)

    scored = score_categories(aggregates)

    with session_scope() as session:
        for s in scored:
            session.add(
                CategoryScore(
                    genre_id=s.aggregate.genre_id,
                    country=cc,
                    num_apps=s.aggregate.num_apps,
                    avg_rating_top=s.aggregate.avg_rating_top,
                    total_rating_count=s.aggregate.total_rating_count,
                    median_rating_count=s.aggregate.median_rating_count,
                    num_strong_incumbents=s.aggregate.num_strong_incumbents,
                    num_mega_incumbents=s.aggregate.num_mega_incumbents,
                    num_stale_incumbents=s.aggregate.num_stale_incumbents,
                    median_days_since_update=s.aggregate.median_days_since_update,
                    num_developers=s.aggregate.num_developers,
                    top_dev_share=s.aggregate.top_dev_share,
                    english_only_share=s.aggregate.english_only_share,
                    num_declining_incumbents=s.aggregate.num_declining_incumbents,
                    monetization_score=s.aggregate.monetization_score,
                    paid_share=s.aggregate.paid_share,
                    newcomer_share=s.aggregate.newcomer_share,
                    demand_score=s.demand_score,
                    quality_gap_score=s.quality_gap_score,
                    low_saturation_score=s.low_saturation_score,
                    momentum_score=s.momentum_score,
                    rank_momentum=s.rank_momentum,
                    contestability=s.contestability,
                    opportunity_score=s.opportunity_score,
                    est_cpi_pln=s.marketing.est_cpi_pln,
                    est_installs_month=s.marketing.est_installs_month,
                    marketing_cost_pln=s.marketing.marketing_cost_pln,
                    success_probability=s.marketing.success_probability,
                )
            )
    logger.info("Stored scores for %d categories (%s)", len(scored), cc)
    return scored
