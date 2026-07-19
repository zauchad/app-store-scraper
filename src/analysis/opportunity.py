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
from src.db.models import Category, CategoryScore
from src.db.session import session_scope
from src.logging_config import get_logger

logger = get_logger(__name__)

# Base weights (used when momentum history exists). Renormalised without
# momentum on day 1.
WEIGHTS = {
    "demand": 0.25,
    "quality_gap": 0.30,
    "low_saturation": 0.20,
    "momentum": 0.25,
}

# Absolute quality bar: incumbents rated at/above this = essentially no gap.
QUALITY_BAR = 4.6
QUALITY_GAP_SPAN = 1.0  # gap saturates once incumbents are ~1.0 star below bar


@dataclass
class ScoredCategory:
    aggregate: CategoryAggregate
    demand_score: float
    quality_gap_score: float
    low_saturation_score: float
    momentum_score: float
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


def _contestability(num_mega: int, num_fortress: int) -> float:
    """0..1 multiplier: can a lean founder realistically contest this market?

    * mega giants dominate the penalty (each one roughly halves the chance).
    * fortresses add a softer, saturation-style penalty.
    sqrt softens the product so a single fortress doesn't nuke the score.
    """
    mega_penalty = 1.0 / (1.0 + num_mega)
    fortress_penalty = 1.0 / (1.0 + num_fortress / 8.0)
    return math.sqrt(mega_penalty * fortress_penalty)


def score_categories(aggregates: List[CategoryAggregate]) -> List[ScoredCategory]:
    if not aggregates:
        return []

    # DEMAND: log-scaled median review count, normalised across categories.
    demand_raw = [math.log1p(max(a.median_rating_count, 0)) for a in aggregates]
    # SATURATION: number of fortresses, normalised.
    sat_raw = [float(a.num_strong_incumbents) for a in aggregates]
    mom_raw = [a.raw_momentum for a in aggregates]

    demand_n = _minmax(demand_raw)
    sat_n = _minmax(sat_raw)
    mom_n = _minmax(mom_raw)

    has_momentum = any(abs(m) > 1e-9 for m in mom_raw)
    weights = _effective_weights(has_momentum)

    cpi_by_genre = _cpi_lookup()

    scored: List[ScoredCategory] = []
    for i, agg in enumerate(aggregates):
        demand = demand_n[i]
        quality_gap = _absolute_quality_gap(agg.avg_rating_top)
        low_saturation = 1.0 - sat_n[i]
        momentum = mom_n[i] if has_momentum else 0.0

        attractiveness = (
            weights["demand"] * demand
            + weights["quality_gap"] * quality_gap
            + weights["low_saturation"] * low_saturation
            + weights["momentum"] * momentum
        )
        contest = _contestability(
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
                contestability=round(contest, 4),
                opportunity_score=opp,
                marketing=mkt,
            )
        )

    scored.sort(key=lambda s: s.opportunity_score, reverse=True)
    return scored


def _absolute_quality_gap(avg_rating: float | None) -> float:
    """How far incumbents sit below the quality bar, clamped to 0..1.

    avg 4.6+ -> 0.0 (no gap); avg 3.6 -> 1.0 (wide open). Missing -> mild 0.4.
    """
    if avg_rating is None:
        return 0.4
    gap = (QUALITY_BAR - avg_rating) / QUALITY_GAP_SPAN
    return max(0.0, min(1.0, gap))


def _effective_weights(has_momentum: bool) -> Dict[str, float]:
    if has_momentum:
        return WEIGHTS
    # Drop momentum and renormalise the rest so they still sum to 1.
    base = {k: v for k, v in WEIGHTS.items() if k != "momentum"}
    total = sum(base.values())
    weights = {k: v / total for k, v in base.items()}
    weights["momentum"] = 0.0
    return weights


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
                    median_rating_count=s.aggregate.median_rating_count,
                    num_strong_incumbents=s.aggregate.num_strong_incumbents,
                    num_mega_incumbents=s.aggregate.num_mega_incumbents,
                    demand_score=s.demand_score,
                    quality_gap_score=s.quality_gap_score,
                    low_saturation_score=s.low_saturation_score,
                    momentum_score=s.momentum_score,
                    contestability=s.contestability,
                    opportunity_score=s.opportunity_score,
                    est_cpi_pln=s.marketing.est_cpi_pln,
                    est_installs_month=s.marketing.est_installs_month,
                    marketing_cost_pln=s.marketing.marketing_cost_pln,
                    success_probability=s.marketing.success_probability,
                )
            )
    logger.info("Stored scores for %d categories", len(scored))
    return scored
