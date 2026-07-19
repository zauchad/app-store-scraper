"""Pluggable review-text providers (MODE A fuel).

Why an abstraction: as of 2026 Apple killed free anonymous access to review TEXT
(RSS feed returns empty, AMP API needs a server-side token -> 401). So getting
real review text needs either a hosted API or a headless browser. We isolate
that choice behind `ReviewProvider` so the pipeline never changes when you swap
sources.

Implementations:
  * RssReviewProvider     - free legacy feed. Best effort; usually empty now.
  * RapidApiReviewProvider - any hosted App Store reviews API on RapidAPI.
        Configure with RAPIDAPI_KEY + RAPIDAPI_HOST + RAPIDAPI_REVIEWS_URL.
        The response parser is defensive and accepts the common field names
        used across providers (rating/score, review/body/content/text, ...).

Add a paid/browser provider later by subclassing `ReviewProvider` and returning
it from `get_review_provider()`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import settings
from src.logging_config import get_logger
from src.scraper.itunes_client import ItunesClient

logger = get_logger(__name__)


@dataclass
class ReviewRecord:
    review_id: str
    author: Optional[str]
    title: Optional[str]
    body: Optional[str]
    rating: Optional[int]
    version: Optional[str] = None
    review_date: Optional[datetime] = None


class ReviewProvider:
    """Interface. `fetch` returns a list of normalised reviews for one app."""

    name = "base"

    def fetch(self, app_id: int, max_reviews: int) -> List[ReviewRecord]:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
#  Free legacy RSS
# --------------------------------------------------------------------------- #
class RssReviewProvider(ReviewProvider):
    name = "rss"

    def __init__(self, country: str) -> None:
        self._client = ItunesClient(country=country)

    def fetch(self, app_id: int, max_reviews: int) -> List[ReviewRecord]:
        pages = max(1, min(settings.review_pages_per_app, 10))
        items = self._client.reviews(app_id, pages=pages)
        out = [
            ReviewRecord(
                review_id=i.review_id,
                author=i.author,
                title=i.title,
                body=i.body,
                rating=i.rating,
                version=i.version,
            )
            for i in items
        ]
        return out[:max_reviews]


# --------------------------------------------------------------------------- #
#  Hosted RapidAPI (cheap, reliable, headless-friendly)
# --------------------------------------------------------------------------- #
class RapidApiReviewProvider(ReviewProvider):
    name = "rapidapi"

    def __init__(self, key: str, host: str, url_template: str, country: str) -> None:
        if not (key and host and url_template):
            raise ValueError(
                "RapidAPI provider requires RAPIDAPI_KEY, RAPIDAPI_HOST and "
                "RAPIDAPI_REVIEWS_URL to be set."
            )
        self._key = key
        self._host = host
        self._url_template = url_template
        self._country = country
        self._session = requests.Session()
        self._session.headers.update(
            {"X-RapidAPI-Key": key, "X-RapidAPI-Host": host}
        )

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _get(self, url: str) -> Any:
        resp = self._session.get(url, timeout=25)
        resp.raise_for_status()
        return resp.json()

    def fetch(self, app_id: int, max_reviews: int) -> List[ReviewRecord]:
        out: List[ReviewRecord] = []
        page = 1
        while len(out) < max_reviews and page <= 10:
            url = self._url_template.format(
                app_id=app_id, country=self._country, page=page
            )
            try:
                data = self._get(url)
            except Exception as exc:  # noqa: BLE001
                logger.warning("RapidAPI reviews failed app=%s page=%s: %s", app_id, page, exc)
                break
            items = _extract_items(data)
            if not items:
                break
            for raw in items:
                rec = _parse_generic_review(raw, app_id, page, len(out))
                if rec:
                    out.append(rec)
            page += 1
        return out[:max_reviews]


def _extract_items(data: Any) -> List[Dict[str, Any]]:
    """Find the list of reviews in a variety of response shapes."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("reviews", "data", "results", "items", "reviewList"):
            val = data.get(key)
            if isinstance(val, list):
                return val
            if isinstance(val, dict):
                for k2 in ("reviews", "data", "results", "items"):
                    if isinstance(val.get(k2), list):
                        return val[k2]
    return []


def _first(raw: Dict[str, Any], keys: List[str]) -> Optional[Any]:
    for k in keys:
        if k in raw and raw[k] not in (None, ""):
            return raw[k]
        # nested attributes (e.g. AMP-style {"attributes": {...}})
        attrs = raw.get("attributes")
        if isinstance(attrs, dict) and attrs.get(k) not in (None, ""):
            return attrs[k]
    return None


def _parse_generic_review(
    raw: Dict[str, Any], app_id: int, page: int, idx: int
) -> Optional[ReviewRecord]:
    if not isinstance(raw, dict):
        return None
    rid = _first(raw, ["id", "reviewId", "review_id"]) or f"{app_id}-{page}-{idx}"
    rating = _first(raw, ["rating", "score", "star", "stars"])
    try:
        rating = int(round(float(rating))) if rating is not None else None
    except (TypeError, ValueError):
        rating = None
    body = _first(raw, ["review", "body", "content", "text", "comment"])
    title = _first(raw, ["title", "headline", "subject"])
    author = _first(raw, ["author", "userName", "user_name", "username", "nickname"])
    version = _first(raw, ["version", "appVersion", "app_version"])
    if isinstance(author, dict):
        author = author.get("name") or author.get("label")
    return ReviewRecord(
        review_id=str(rid),
        author=str(author) if author else None,
        title=str(title) if title else None,
        body=str(body) if body else None,
        rating=rating,
        version=str(version) if version else None,
    )


def get_review_provider() -> ReviewProvider:
    provider = settings.review_provider.lower()
    if provider == "rapidapi":
        return RapidApiReviewProvider(
            key=settings.rapidapi_key,
            host=settings.rapidapi_host,
            url_template=settings.rapidapi_reviews_url,
            country=settings.store_country,
        )
    return RssReviewProvider(country=settings.store_country)
