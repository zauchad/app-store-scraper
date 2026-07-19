"""Central configuration.

Everything is driven by environment variables (see `.env.example`) so the same
codebase runs locally (SQLite, no setup) and in production (Supabase Postgres +
Streamlit Cloud + GitHub Actions) without code changes.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root (…/app-store-scraper)
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"


class Settings(BaseSettings):
    """Typed settings loaded from the environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database ---
    database_url: str = ""

    # --- LLM ---
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    llm_provider: str = "gemini"
    # Min seconds between LLM calls (respect per-minute rate limits, ~15 RPM).
    llm_min_interval_seconds: float = 4.0
    # Retries for transient (per-minute) 429s before giving up on a call.
    llm_max_retries: int = 3

    # --- Scraper ---
    store_country: str = "us"
    top_n_apps: int = 50
    charts: str = "topfree"
    excluded_genre_ids: str = "6014"
    review_pages_per_app: int = 5

    # --- Review provider (MODE A fuel) ---
    # "rss"      -> free legacy feed (mostly empty in 2026, kept as fallback)
    # "rapidapi" -> hosted App Store reviews API (cheap, reliable, headless)
    review_provider: str = "rss"
    rapidapi_key: str = ""
    rapidapi_host: str = ""
    # URL template with {app_id}, {country}, {page} placeholders.
    rapidapi_reviews_url: str = ""
    max_reviews_per_app: int = 100

    # --- Business / marketing ---
    marketing_budget_pln: float = 7500.0
    usd_pln_rate: float = 4.0

    # --- Deep dive ---
    deep_dive_top_k: int = 5

    # --- Micro-niche discovery ---
    # Search-interest proxy: "proxy" (free autocomplete) or "none".
    volume_provider: str = "proxy"
    # Weight of search-interest vs app-engagement in keyword demand (0..1).
    demand_search_weight: float = 0.5
    # Auto-discovery: how many top categories to drill into, keywords each.
    discover_top_categories: int = 5
    discover_keywords_per_category: int = 12

    # ---- Derived helpers -------------------------------------------------
    @property
    def resolved_database_url(self) -> str:
        """Return a usable DB URL, falling back to a local SQLite file."""
        if self.database_url.strip():
            return self.database_url.strip()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{DATA_DIR / 'market_intel.db'}"

    @property
    def chart_list(self) -> List[str]:
        mapping = {
            "topfree": "topfreeapplications",
            "toppaid": "toppaidapplications",
            "topgrossing": "topgrossingapplications",
        }
        out: List[str] = []
        for c in self.charts.split(","):
            c = c.strip().lower()
            if c in mapping:
                out.append(mapping[c])
        return out or ["topfreeapplications"]

    @property
    def excluded_genres(self) -> List[int]:
        ids: List[int] = []
        for x in self.excluded_genre_ids.split(","):
            x = x.strip()
            if x.isdigit():
                ids.append(int(x))
        return ids

    @property
    def llm_enabled(self) -> bool:
        return bool(self.gemini_api_key.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
