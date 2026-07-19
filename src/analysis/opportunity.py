"""Opportunity Score = the headline business conclusion of Level 1.

We normalise each raw signal *across all categories in the run* (relative min-max)
because "high demand" only means something compared to other niches today. Then
we combine them with tunable weights into a single 0..100 score, and attach the
marketing feasibility estimate.

    Opportunity = 100 * ( w_demand   * demand
                        + w_gap      * quality_gap
                        + w_sat      * low_saturation
                        + w_momentum * momentum )

Reading it:
  * HIGH demand + HIGH quality_gap + LOW saturation = classic underserved niche.
  * Momentum breaks ties and flags niches that are actively heating up.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from sqlalchemy.orm import Session

from src.analysis.marketing import MarketingEstimate, estimate
from src.analysis.metrics import CategoryAggregate, compute_all_aggregates
from src.db.models import Category, CategoryScore
from src.db.session import session_scope
from src.logging_config import get_logger

logger = get_logger(__name__)

WEIGHTS = {
    "demand": 0.30,
    "quality_gap": 0.30,
    "low_saturation": 0.25,
    "momentum": 0.15,
}


@dataclass
class ScoredCategory:
    aggregate: CategoryAggregate
    demand_score: float
    quality_gap_score: float
    low_saturation_score: float
    momentum_score: float
    opportunity_score: float
    marketing: MarketingEstimate


def _minmax(values: List[float]) -> Dict[int, float]:
    """Return index -> normalised 0..1. Flat input -> all 0.5 (neutral)."""
    if not values:
        return {}
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return {i: 0.5 for i in range(len(values))}
    return {i: (v - lo) / (hi - lo) for i, v in enumerate(values)}


def score_categories(aggregates: List[CategoryAggregate]) -> List[ScoredCategory]:
    if not aggregates:
        return []

    demand_raw = [float(a.total_rating_count) for a in aggregates]
    # quality gap: lower avg rating => bigger gap. Missing rating => neutral 3.5.
    gap_raw = [5.0 - (a.avg_rating_top if a.avg_rating_top is not None else 3.5) for a in aggregates]
    sat_raw = [float(a.num_strong_incumbents) for a in aggregates]
    mom_raw = [a.raw_momentum for a in aggregates]

    demand_n = _minmax(demand_raw)
    gap_n = _minmax(gap_raw)
    sat_n = _minmax(sat_raw)
    mom_n = _minmax(mom_raw)

    # Need category CPI benchmarks for the marketing layer.
    cpi_by_genre = _cpi_lookup()

    scored: List[ScoredCategory] = []
    for i, agg in enumerate(aggregates):
        demand = demand_n[i]
        quality_gap = gap_n[i]
        low_saturation = 1.0 - sat_n[i]
        momentum = mom_n[i]

        opp = 100.0 * (
            WEIGHTS["demand"] * demand
            + WEIGHTS["quality_gap"] * quality_gap
            + WEIGHTS["low_saturation"] * low_saturation
            + WEIGHTS["momentum"] * momentum
        )
        opp = round(opp, 2)

        mkt = estimate(
            base_cpi_usd=cpi_by_genre.get(agg.genre_id, 3.0),
            opportunity_0_100=opp,
            quality_gap_0_1=quality_gap,
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


def compute_and_store() -> List[ScoredCategory]:
    """Compute aggregates, score, and persist a CategoryScore row per category."""
    with session_scope() as session:
        aggregates = compute_all_aggregates(session)

    scored = score_categories(aggregates)

    with session_scope() as session:
        for s in scored:
            session.add(
                CategoryScore(
                    genre_id=s.aggregate.genre_id,
                    num_apps=s.aggregate.num_apps,
                    avg_rating_top=s.aggregate.avg_rating_top,
                    total_rating_count=s.aggregate.total_rating_count,
                    num_strong_incumbents=s.aggregate.num_strong_incumbents,
                    demand_score=s.demand_score,
                    quality_gap_score=s.quality_gap_score,
                    low_saturation_score=s.low_saturation_score,
                    momentum_score=s.momentum_score,
                    opportunity_score=s.opportunity_score,
                    est_cpi_pln=s.marketing.est_cpi_pln,
                    est_installs_month=s.marketing.est_installs_month,
                    marketing_cost_pln=s.marketing.marketing_cost_pln,
                    success_probability=s.marketing.success_probability,
                )
            )
    logger.info("Stored scores for %d categories", len(scored))
    return scored
