"""Marketing feasibility layer.

A niche with a huge quality gap is worthless if you cannot *afford* to acquire
users. This module answers the question you actually care about:

  "With my monthly budget (default 7500 PLN), can I realistically buy enough
   installs to matter in this niche - and what are my odds?"

All numbers are transparent heuristics driven by editable CPI benchmarks. They
are meant to *rank and filter* niches by feasibility, not to be exact forecasts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.config import settings


@dataclass
class MarketingEstimate:
    est_cpi_pln: float
    est_installs_month: int
    marketing_cost_pln: float  # = full budget (what it costs to run this)
    reach_ratio: float  # installs you can buy vs typical incumbent scale
    success_probability: float  # 0..1


def _normalized_incumbent_scale(total_rating_count: int, num_apps: int) -> float:
    """Rough proxy for 'how big is the average serious player here'.

    Reviews are ~1-5% of installs, so we scale up to approximate install base.
    """
    if num_apps <= 0:
        return 1.0
    avg_reviews = total_rating_count / num_apps
    # assume reviews ~2% of lifetime installs
    return max(avg_reviews / 0.02, 1.0)


def estimate(
    base_cpi_usd: float,
    opportunity_0_100: float,
    quality_gap_0_1: float,
    contestability: float,
    total_rating_count: int,
    num_apps: int,
    budget_pln: Optional[float] = None,
) -> MarketingEstimate:
    budget = budget_pln if budget_pln is not None else settings.marketing_budget_pln
    cpi_pln = round(base_cpi_usd * settings.usd_pln_rate, 2)
    installs = int(budget / cpi_pln) if cpi_pln > 0 else 0

    incumbent_scale = _normalized_incumbent_scale(total_rating_count, num_apps)
    # Monthly paid reach as a fraction of an average incumbent's install base.
    # (12 months of budget vs their lifetime scale -> annualised comparison.)
    reach_ratio = min((installs * 12) / incumbent_scale, 1.0)

    success = _success_probability(
        opportunity_0_100 / 100.0, quality_gap_0_1, reach_ratio, contestability
    )

    return MarketingEstimate(
        est_cpi_pln=cpi_pln,
        est_installs_month=installs,
        marketing_cost_pln=round(budget, 2),
        reach_ratio=round(reach_ratio, 4),
        success_probability=round(success, 4),
    )


def _success_probability(
    opportunity: float, quality_gap: float, reach_ratio: float, contestability: float
) -> float:
    """Blend four drivers into a 0..1 odds estimate.

      * opportunity     - is the niche structurally attractive?
      * quality_gap     - room for a better product = organic/word-of-mouth upside
      * reach_ratio     - can the budget buy a foothold vs incumbents?
      * contestability  - can a lean player even compete (giant guardrail)?

    Weighted, then squashed so extremes stay in (0,1).
    """
    raw = (
        0.30 * opportunity
        + 0.25 * quality_gap
        + 0.20 * reach_ratio
        + 0.25 * contestability
    )
    # gentle floor/ceiling so nothing reads as 0% or 100%
    return max(0.03, min(0.97, raw))
