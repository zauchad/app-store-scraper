"""Shared scoring primitives used by BOTH category and micro-niche (keyword)
analysis, so the mental model stays identical everywhere:

    Opportunity = attractiveness x contestability

  * attractiveness = demand + quality_gap + low_saturation (+ momentum)
  * contestability = can a LEAN founder even compete (giant guardrail)?

Keeping these here (instead of duplicating in each analyzer) guarantees that a
"70" at category level means the same thing as a "70" at keyword level.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

# --- Incumbent thresholds (single source of truth) ------------------------- #
# A "fortress" is a serious, established player (loved AND sizeable).
FORTRESS_MIN_RATING = 4.3
FORTRESS_MIN_REVIEWS = 50_000
# A "mega" incumbent is a market-owning giant you cannot out-spend on a lean
# budget. Their presence collapses contestability.
MEGA_MIN_REVIEWS = 3_000_000

# --- Quality gap ----------------------------------------------------------- #
QUALITY_BAR = 4.6      # incumbents at/above this = essentially no gap
QUALITY_GAP_SPAN = 1.0  # gap saturates ~1.0 star below the bar

# --- Update cadence -------------------------------------------------------- #
# A sizeable app not updated in this many days looks "abandoned" - a fresh
# opening even if it still has lots of legacy reviews.
STALE_DAYS = 365

# --- Base component weights (momentum dropped + renormalised when no history) #
WEIGHTS = {
    "demand": 0.25,
    "quality_gap": 0.30,
    "low_saturation": 0.20,
    "momentum": 0.25,
}


def absolute_quality_gap(avg_rating: Optional[float]) -> float:
    """How far incumbents sit below the quality bar, clamped to 0..1.

    avg 4.6+ -> 0.0 (no gap); avg 3.6 -> 1.0 (wide open). Missing -> mild 0.4.
    """
    if avg_rating is None:
        return 0.4
    gap = (QUALITY_BAR - avg_rating) / QUALITY_GAP_SPAN
    return max(0.0, min(1.0, gap))


# --- Keyword (ASO) difficulty ---------------------------------------------- #
# Median top-app ratings at which ranking difficulty ~saturates.
DIFFICULTY_REF = 500_000


def keyword_difficulty(
    median_top_ratings: int, num_fortress: int, num_mega: int, top_n: int
) -> float:
    """0..1 ASO difficulty: how hard to out-rank the apps already on this term.

    Driven by the *authority* of apps currently ranking (rating volume), the
    share of entrenched fortresses, and a bump for any mega giants. This is the
    AppTweak-style "difficulty" that pairs with search-interest ("volume"):
    the sweet spot is HIGH interest + LOW difficulty.
    """
    strength = min(math.log1p(max(median_top_ratings, 0)) / math.log1p(DIFFICULTY_REF), 1.0)
    fortress_share = min(num_fortress / max(top_n, 1), 1.0)
    mega_bump = min(num_mega * 0.15, 0.3)
    diff = 0.55 * strength + 0.45 * fortress_share + mega_bump
    return round(min(max(diff, 0.0), 1.0), 4)


def contestability(num_mega: int, num_fortress: int) -> float:
    """0..1 multiplier: can a lean founder realistically contest this market?

    * mega giants dominate the penalty (each roughly halves the chance).
    * fortresses add a softer, saturation-style penalty.
    sqrt softens the product so a single fortress doesn't nuke the score.
    """
    mega_penalty = 1.0 / (1.0 + num_mega)
    fortress_penalty = 1.0 / (1.0 + num_fortress / 8.0)
    return math.sqrt(mega_penalty * fortress_penalty)


def effective_weights(has_momentum: bool) -> Dict[str, float]:
    """Full weights when momentum data exists; otherwise drop + renormalise."""
    if has_momentum:
        return dict(WEIGHTS)
    base = {k: v for k, v in WEIGHTS.items() if k != "momentum"}
    total = sum(base.values())
    weights = {k: v / total for k, v in base.items()}
    weights["momentum"] = 0.0
    return weights


def count_incumbents(rows: List[tuple]) -> tuple:
    """Given [(rating_avg, rating_count), ...] return (num_fortress, num_mega)."""
    fortress = sum(
        1
        for r, c in rows
        if (r or 0) >= FORTRESS_MIN_RATING and (c or 0) >= FORTRESS_MIN_REVIEWS
    )
    mega = sum(1 for _, c in rows if (c or 0) >= MEGA_MIN_REVIEWS)
    return fortress, mega
