"""Ingestion: pull from Apple -> normalise -> persist to DB.

Flow per run:
  1. Ensure category rows exist (seed).
  2. For each enabled category: pull top chart(s) -> upsert apps.
  3. Batch-lookup exact rating metadata -> write one AppSnapshot per app
     (this is the time-series row that later powers momentum).
  4. Optionally pull reviews (best effort) -> upsert reviews.

Everything is idempotent and resilient: a failure in one category is logged and
skipped, never aborting the whole scan.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import settings
from src.db.models import App, AppSnapshot, Category, Review
from src.db.session import init_db, session_scope
from src.logging_config import get_logger
from src.scraper.categories import CATEGORY_SEEDS, get_category_seeds
from src.scraper.itunes_client import ChartEntry, ItunesClient
from src.scraper.review_providers import get_review_provider

logger = get_logger(__name__)


def ensure_categories(session: Session) -> None:
    """Upsert the seed categories (finite, known set)."""
    for seed in CATEGORY_SEEDS:
        cat = session.get(Category, seed.genre_id)
        if cat is None:
            session.add(
                Category(
                    genre_id=seed.genre_id,
                    name=seed.name,
                    is_games=seed.is_games,
                    enabled=seed.enabled,
                    base_cpi_usd=seed.base_cpi_usd,
                )
            )
        else:
            cat.name = seed.name
            cat.is_games = seed.is_games
            cat.base_cpi_usd = seed.base_cpi_usd


def _upsert_app(session: Session, entry: ChartEntry) -> None:
    app = session.get(App, entry.app_id)
    if app is None:
        session.add(
            App(
                id=entry.app_id,
                name=entry.name,
                developer=entry.developer,
                genre_id=entry.genre_id,
                price=entry.price,
                currency=entry.currency,
                url=entry.url,
                icon_url=entry.icon_url,
            )
        )
    else:
        app.name = entry.name or app.name
        app.developer = entry.developer or app.developer
        if entry.genre_id:
            app.genre_id = entry.genre_id
        app.price = entry.price
        app.icon_url = entry.icon_url or app.icon_url
        app.url = entry.url or app.url


def scrape_all(fetch_reviews: bool = True) -> Dict[str, int]:
    """Run a full ingestion pass. Returns simple counters for logging/monitoring."""
    init_db()
    client = ItunesClient(country=settings.store_country)
    seeds = get_category_seeds(settings.excluded_genres)
    counters = {"categories": 0, "apps": 0, "snapshots": 0, "reviews": 0}

    for seed in seeds:
        try:
            counters["categories"] += 1
            _scrape_category(client, seed.genre_id, fetch_reviews, counters)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Category %s failed: %s", seed.genre_id, exc)

    logger.info("Ingestion done: %s", counters)
    return counters


def _scrape_category(
    client: ItunesClient,
    genre_id: int,
    fetch_reviews: bool,
    counters: Dict[str, int],
) -> None:
    # Collect chart entries (dedupe across chart types, keep best rank).
    best_entry: Dict[int, ChartEntry] = {}
    for chart in settings.chart_list:
        for entry in client.top_chart(chart, genre_id, settings.top_n_apps):
            existing = best_entry.get(entry.app_id)
            if existing is None or entry.rank < existing.rank:
                best_entry[entry.app_id] = entry

    if not best_entry:
        return

    app_ids = list(best_entry.keys())
    metadata = client.lookup(app_ids)

    with session_scope() as session:
        ensure_categories(session)
        for app_id, entry in best_entry.items():
            _upsert_app(session, entry)
            counters["apps"] += 1
            meta = metadata.get(app_id)
            session.add(
                AppSnapshot(
                    app_id=app_id,
                    genre_id=genre_id,
                    chart_type=settings.chart_list[0],
                    rank=entry.rank,
                    rating_avg=meta.rating_avg if meta else None,
                    rating_count=meta.rating_count if meta else None,
                    version=meta.version if meta else None,
                    current_version_release_date=(
                        meta.current_version_release_date if meta else None
                    ),
                )
            )
            counters["snapshots"] += 1
            # persist app-level metadata (description + free date signals)
            if meta:
                app = session.get(App, app_id)
                if app is not None:
                    if meta.description:
                        app.description = meta.description[:4000]
                    if meta.release_date:
                        app.release_date = meta.release_date
                    if meta.current_version_release_date:
                        app.current_version_release_date = (
                            meta.current_version_release_date
                        )

    if fetch_reviews:
        _scrape_reviews_for_category(app_ids, counters)


def _scrape_reviews_for_category(
    app_ids: List[int], counters: Dict[str, int]
) -> None:
    provider = get_review_provider()
    logger.info("Fetching reviews via provider=%s", provider.name)
    # An app can appear in several charts of the same category; fetch it once.
    for app_id in dict.fromkeys(app_ids):
        try:
            reviews = provider.fetch(app_id, settings.max_reviews_per_app)
        except Exception as exc:  # noqa: BLE001 - one app must not kill the run
            logger.warning("Review fetch failed app=%s: %s", app_id, exc)
            continue
        if not reviews:
            continue
        seen: set = set()  # RSS can repeat the same review id across pages
        with session_scope() as session:
            for r in reviews:
                if r.review_id in seen:
                    continue
                seen.add(r.review_id)
                if session.get(Review, r.review_id) is not None:
                    continue
                session.add(
                    Review(
                        id=r.review_id,
                        app_id=app_id,
                        author=r.author,
                        title=r.title,
                        body=r.body,
                        rating=r.rating,
                        version=r.version,
                        review_date=r.review_date,
                    )
                )
                counters["reviews"] += 1
