"""Storefronts we collect in scheduled scans and expose in the dashboard."""
from __future__ import annotations

STOREFRONTS: dict[str, str] = {
    "us": "US — Stany Zjednoczone",
    "pl": "PL — Polska",
}

# LLM steps (deep-dive, discover) run against this market's category scores.
PRIMARY_STOREFRONT = "us"

SCAN_COUNTRIES = tuple(STOREFRONTS)


def normalize_country(code: str) -> str:
    return code.strip().lower()
