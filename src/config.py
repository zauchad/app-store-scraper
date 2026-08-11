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
    # Comma-separated Google AI Studio keys. When the daily free-tier quota of
    # one key is hit (429 PerDay), we rotate to the next -> multiplies daily
    # capacity. Keys from DIFFERENT Google Cloud projects have independent quotas.
    # A single key works too (no commas needed).
    gemini_api_keys: str = ""
    # "gemini-2.5-flash" is no longer available to NEW API projects (404). Use the
    # forward-compatible alias that always points to the current flash model.
    gemini_model: str = "gemini-flash-latest"
    llm_provider: str = "gemini"
    # Min seconds between LLM calls (respect per-minute rate limits, ~15 RPM).
    llm_min_interval_seconds: float = 4.0
    # Retries for transient (per-minute) 429s before giving up on a call.
    llm_max_retries: int = 3

    # --- Scraper ---
    store_country: str = "us"
    top_n_apps: int = 50
    # topgrossing = the only free "people actually PAY here" proxy; keep it on.
    charts: str = "topfree,topgrossing"
    excluded_genre_ids: str = "6014"
    review_pages_per_app: int = 5

    # --- Apple Ads (Search Ads) popularity provider - FREE, needs account ---
    # Account Settings -> API in the Apple Ads UI: upload a public key, copy
    # clientId / teamId / keyId. No ad spend required to query the API.
    asa_client_id: str = ""
    asa_team_id: str = ""
    asa_key_id: str = ""
    # PEM inline (with \n) or a path to the .pem file.
    asa_private_key: str = ""
    asa_org_id: str = ""
    # Popularity endpoint template with {term} and {country} placeholders.
    asa_popularity_url: str = ""
    # Optional JSON body template -> switches the call to POST.
    asa_popularity_body: str = ""

    # --- Reddit demand mining (FREE: script app at reddit.com/prefs/apps) ---
    reddit_client_id: str = ""
    reddit_client_secret: str = ""

    # --- Digest delivery (both optional; free) ---
    slack_webhook_url: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: str = ""  # comma-separated recipients

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

    # --- Monetization (Phase 1) -----------------------------------------------
    monetization_enabled: bool = False
    signup_bonus_credits: int = 0
    pro_monthly_credits: int = 15
    supabase_url: str = ""
    supabase_anon_key: str = ""
    lemonsqueezy_webhook_secret: str = ""
    lemonsqueezy_store_id: str = ""
    lemonsqueezy_variant_1_credit: str = ""
    lemonsqueezy_variant_5_credits: str = ""
    lemonsqueezy_variant_pro: str = ""
    lemonsqueezy_checkout_1_credit: str = ""
    lemonsqueezy_checkout_5_credits: str = ""
    lemonsqueezy_checkout_pro: str = ""
    lemonsqueezy_customer_portal_url: str = ""
    billing_admin_secret: str = ""
    free_daily_keyword_scans: int = 3
    support_email: str = ""
    legal_terms_url: str = ""
    legal_privacy_url: str = ""
    legal_refund_url: str = ""

    # --- Retention ---
    # OFF by default: keep ALL raw daily snapshots indefinitely. Flip to True
    # only if you want to downsample old snapshots to keep the DB flat.
    retention_enabled: bool = False
    # When enabled: keep every daily snapshot for this many days; older ones are
    # downsampled to one per app per ISO-week.
    retention_daily_days: int = 60

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
    def gemini_key_list(self) -> List[str]:
        """Ordered, de-duplicated key pool from GEMINI_API_KEYS."""
        raw = [k.strip() for k in self.gemini_api_keys.split(",") if k.strip()]
        seen, out = set(), []
        for k in raw:
            if k not in seen:
                seen.add(k)
                out.append(k)
        return out

    @property
    def llm_enabled(self) -> bool:
        return bool(self.gemini_key_list)

    @property
    def auth_enabled(self) -> bool:
        return self.monetization_enabled and bool(
            self.supabase_url.strip() and self.supabase_anon_key.strip()
        )

    @property
    def billing_configured(self) -> bool:
        return bool(self.lemonsqueezy_webhook_secret.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
