"""Seed list of App Store categories (Apple genre IDs).

This is a *finite, known* set - that's exactly why the platform never needs the
user to manually pick a category: we scan them all automatically.

`base_cpi_usd` is a rough industry cost-per-install benchmark used by the
marketing feasibility layer. These are editable estimates, not gospel - the
point is to filter out niches you *cannot afford to win* given the budget.

Games (6014) and Kids-heavy verticals are flagged capital-heavy and disabled by
default per the product decision (graphics/production cost too high for MVP).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class CategorySeed:
    genre_id: int
    name: str
    base_cpi_usd: float
    is_games: bool = False
    enabled: bool = True


# CPI benchmarks (USD) are ballpark 2025/26 iOS averages per vertical.
CATEGORY_SEEDS: List[CategorySeed] = [
    CategorySeed(6015, "Finance", 6.0),
    CategorySeed(6020, "Medical", 5.0),
    CategorySeed(6000, "Business", 4.0),
    CategorySeed(6023, "Food & Drink", 2.5),
    CategorySeed(6013, "Health & Fitness", 3.5),
    CategorySeed(6017, "Education", 2.5),
    CategorySeed(6016, "Entertainment", 2.0),
    CategorySeed(6012, "Lifestyle", 2.5),
    CategorySeed(6011, "Music", 2.0),
    CategorySeed(6010, "Navigation", 3.0),
    CategorySeed(6009, "News", 2.0),
    CategorySeed(6008, "Photo & Video", 2.0),
    CategorySeed(6007, "Productivity", 3.0),
    CategorySeed(6006, "Reference", 2.0),
    CategorySeed(6024, "Shopping", 2.0),
    CategorySeed(6005, "Social Networking", 3.0),
    CategorySeed(6004, "Sports", 2.0),
    CategorySeed(6003, "Travel", 3.0),
    CategorySeed(6002, "Utilities", 1.5),
    CategorySeed(6001, "Weather", 1.5),
    CategorySeed(6018, "Books", 1.8),
    # Capital-heavy: disabled by default.
    CategorySeed(6014, "Games", 1.5, is_games=True, enabled=False),
]


def get_category_seeds(excluded_genre_ids: List[int]) -> List[CategorySeed]:
    """Return enabled categories, minus any explicitly excluded genre IDs."""
    excluded = set(excluded_genre_ids)
    return [
        c for c in CATEGORY_SEEDS if c.enabled and c.genre_id not in excluded
    ]
