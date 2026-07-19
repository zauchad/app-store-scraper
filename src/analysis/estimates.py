"""Heuristic install / revenue BANDS - honest order-of-magnitude estimates.

IMPORTANT - read this before trusting a number:
  These are NOT measured downloads. Real install/revenue data comes from panel-
  based tools (Sensor Tower, data.ai) behind paid APIs. Here we infer an
  order-of-magnitude BAND from the only public signal we have: the public rating
  count. It is deliberately shown as a wide range and always labelled "≈ / heur."

Why it's still useful: for RANKING and FILTERING niches ("is the typical app here
a 5k-download hobby project or a 500k-download business?"), an order-of-magnitude
band captures ~80% of the value of paid estimates - which is exactly this tool's
job. It is NOT suitable for due-diligence or valuation.

Model:
  lifetime_installs ~= rating_count / rating_rate
  where rating_rate (share of installers who leave a rating) is ~1-3%. Using the
  1%-3% span gives a natural low/high band:
      low  = rating_count / 0.03
      high = rating_count / 0.01
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

RATING_RATE_LOW = 0.01   # optimistic (few rate) -> higher install estimate
RATING_RATE_HIGH = 0.03  # conservative (many rate) -> lower install estimate


@dataclass
class InstallBand:
    low: int
    high: int

    @property
    def label(self) -> str:
        if self.high <= 0:
            return "≈ <1k (heur.)"
        return f"≈ {_humanize(self.low)}–{_humanize(self.high)} (heur.)"


def _humanize(n: float) -> str:
    n = max(n, 0)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(int(n))


def lifetime_installs(rating_count: Optional[int]) -> InstallBand:
    """Order-of-magnitude LIFETIME installs band from public rating count."""
    rc = int(rating_count or 0)
    if rc <= 0:
        return InstallBand(0, 0)
    low = int(rc / RATING_RATE_HIGH)   # conservative floor
    high = int(rc / RATING_RATE_LOW)   # optimistic ceiling
    return InstallBand(low, high)


def monthly_installs(daily_review_delta: Optional[float]) -> Optional[InstallBand]:
    """Rough MONTHLY installs band from review velocity (needs history).

    new_reviews_per_month = daily_review_delta * 30
    monthly_installs ~= new_reviews_per_month / rating_rate
    Returns None when we have no velocity signal yet.
    """
    if daily_review_delta is None or daily_review_delta <= 0:
        return None
    monthly_reviews = daily_review_delta * 30.0
    low = int(monthly_reviews / RATING_RATE_HIGH)
    high = int(monthly_reviews / RATING_RATE_LOW)
    return InstallBand(low, high)


def paid_revenue_band(band: InstallBand, price: float) -> Optional[str]:
    """Gross lifetime revenue band for PAID apps only (price > 0).

    For freemium/IAP apps we cannot estimate revenue without monetisation data,
    so we return None (honest) rather than a fabricated number.
    """
    if not price or price <= 0:
        return None
    low = band.low * price
    high = band.high * price
    return f"≈ ${_humanize(low)}–{_humanize(high)} (heur., cena × instalacje)"
