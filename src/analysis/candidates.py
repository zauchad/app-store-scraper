""""Clone-and-improve" candidate ranking.

Given the apps that already compete in a niche (a category or a keyword), which
ones are the best *templates to beat*? The winning pattern for a lean founder is
almost never a brand-new category - it is an app that already PROVES demand
(many users) but has an exploitable WEAKNESS (mediocre rating and/or neglected
updates). Cloning its core value and fixing the weakness is the realistic path.

This module turns the raw competitor list into a ranked, human-readable shortlist
with an explicit reason ("why beatable") and an improvement angle ("what to fix").
It is pure, dependency-light business logic so it can be unit-tested and reused by
both the category deep-dive and the micro-niche explorer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

# An app needs at least this many ratings to count as "proven demand" - below it
# we cannot tell a real market from a hobby project, so it's a poor template.
MIN_DEMAND_RATINGS = 300
# Rating at/above which an app is considered "loved" (hard to beat on quality).
QUALITY_CEILING = 4.7
# Rating span used to normalise the quality gap (4.7 great -> 3.0 weak).
QUALITY_SPAN = 1.7
# Ratings count that reads as "very strong demand" (normalisation reference).
DEMAND_REF = 200_000
# Days without an update after which an incumbent looks "abandoned".
STALE_DAYS = 365


@dataclass
class Candidate:
    name: str
    developer: Optional[str]
    rating: Optional[float]
    ratings: int
    url: Optional[str]
    app_id: Optional[int]
    days_since_update: Optional[int]
    price: float
    beatability: float          # 0..100, higher = better clone-and-improve target
    reasons: List[str] = field(default_factory=list)
    angle: str = ""


def _demand(ratings: int) -> float:
    if ratings <= 0:
        return 0.0
    return min(math.log1p(ratings) / math.log1p(DEMAND_REF), 1.0)


def _quality_gap(rating: Optional[float]) -> float:
    """0 = loved (hard), 1 = weak (easy to beat on quality)."""
    if rating is None:
        return 0.35  # unknown -> mild, don't over-reward
    return max(0.0, min((QUALITY_CEILING - rating) / QUALITY_SPAN, 1.0))


def _app_store_url(url: Optional[str], app_id: Optional[int]) -> Optional[str]:
    if url:
        return url
    if app_id:
        return f"https://apps.apple.com/app/id{int(app_id)}"
    return None


def _build_reason_angle(
    rating: Optional[float], ratings: int, days: Optional[int], gap: float
) -> tuple:
    reasons: List[str] = []
    reasons.append(f"Udowodniony popyt: ~{ratings:,} ocen".replace(",", " "))
    if rating is not None and rating < QUALITY_CEILING:
        reasons.append(f"Przeciętna ocena {rating:.2f}★ — użytkownicy niezadowoleni")
    if days is not None and days >= STALE_DAYS:
        reasons.append(f"Brak aktualizacji od ~{days // 30} mies. — produkt zaniedbany")

    # Improvement angle keyed to the dominant weakness.
    if days is not None and days >= STALE_DAYS:
        angle = ("Aktywny rozwój + nowoczesny UI: incumbent jest porzucony, "
                 "regularne aktualizacje szybko przechylą oceny na Twoją stronę.")
    elif gap >= 0.5:
        angle = ("Popraw fundament: skup się na najczęstszych skargach (stabilność, "
                 "UX, ceny) — jest duża luka jakościowa do wypełnienia.")
    elif rating is not None and rating < QUALITY_CEILING:
        angle = ("Dopracuj detale i onboarding: rynek jest, ale lider nie jest "
                 "kochany — wygrasz lepszym doświadczeniem i wsparciem.")
    else:
        angle = ("Zawęź pozycjonowanie: wejdź w konkretną pod-grupę odbiorców, "
                 "której lider nie obsługuje dobrze.")
    return reasons, angle


def rank_candidates(apps: List[dict], limit: int = 5) -> List[Candidate]:
    """Rank niche competitors as clone-and-improve targets.

    Each input dict may contain: name, developer, rating, ratings, url, app_id,
    days_since_update, price. Only `name` is strictly required.
    """
    scored: List[Candidate] = []
    for a in apps:
        ratings = int(a.get("ratings") or a.get("rating_count") or 0)
        if ratings < MIN_DEMAND_RATINGS:
            continue
        rating = a.get("rating")
        if rating is None:
            rating = a.get("rating_avg")
        days = a.get("days_since_update")

        demand = _demand(ratings)
        gap = _quality_gap(rating)
        stale_bonus = 1.0 if (days is not None and days >= STALE_DAYS) else 0.0

        # Reward proven demand AND an exploitable weakness. An app with huge
        # demand but a 4.9 rating scores low (not a realistic target).
        beat = 0.45 * demand + 0.40 * gap + 0.15 * stale_bonus
        reasons, angle = _build_reason_angle(rating, ratings, days, gap)

        scored.append(
            Candidate(
                name=a.get("name") or "—",
                developer=a.get("developer"),
                rating=rating,
                ratings=ratings,
                url=_app_store_url(a.get("url"), a.get("app_id") or a.get("id")),
                app_id=a.get("app_id") or a.get("id"),
                days_since_update=days,
                price=float(a.get("price") or 0.0),
                beatability=round(100.0 * beat, 1),
                reasons=reasons,
                angle=angle,
            )
        )

    scored.sort(key=lambda c: c.beatability, reverse=True)
    return scored[:limit]
