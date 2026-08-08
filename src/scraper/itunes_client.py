"""Thin, defensive client for Apple's free, keyless iTunes endpoints.

Sources (all free, no API key, verified working July 2026):
  * Top charts RSS  - reliable, per country + genre
        https://itunes.apple.com/{cc}/rss/{chart}/limit={N}/genre={gid}/json
  * iTunes Lookup   - reliable, exact rating avg/count, version, description
        https://itunes.apple.com/lookup?id={id}&country={cc}
  * Reviews RSS     - BEST EFFORT: sometimes returns an empty feed. We never
        crash on it; quantitative analysis works without review text, and the
        LLM layer simply gets less (or no) fuel for that app.
        https://itunes.apple.com/{cc}/rss/customerreviews/id={id}/sortBy=mostRecent/page={p}/json

Everything is wrapped in retries + timeouts so a single flaky call can't take
down a daily scan of dozens of categories.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.logging_config import get_logger

logger = get_logger(__name__)

BASE = "https://itunes.apple.com"
DEFAULT_TIMEOUT = 20
HEADERS = {"User-Agent": "MarketIntel/0.1 (+research)"}


class ItunesError(Exception):
    pass


@dataclass
class ChartEntry:
    app_id: int
    name: str
    developer: Optional[str]
    genre_id: Optional[int]
    price: float
    currency: Optional[str]
    url: Optional[str]
    icon_url: Optional[str]
    rank: int


@dataclass
class AppMetadata:
    app_id: int
    name: str
    developer: Optional[str] = None
    genre_id: Optional[int] = None
    rating_avg: Optional[float] = None
    rating_count: Optional[int] = None
    version: Optional[str] = None
    price: float = 0.0
    currency: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    icon_url: Optional[str] = None
    # Already present in the Lookup/Search payload - free extra signals:
    release_date: Optional[datetime] = None            # app age
    current_version_release_date: Optional[datetime] = None  # update cadence
    # Publisher analysis: who owns the niche (1 firm with 10 apps vs 10 firms).
    artist_id: Optional[int] = None
    # All genres the app ranks in (cross-category positioning).
    genre_ids: List[int] = field(default_factory=list)
    # Current-version rating vs lifetime = "is the app getting worse RIGHT NOW".
    rating_avg_current: Optional[float] = None
    rating_count_current: Optional[int] = None
    # What the competition just shipped (feature velocity signal).
    release_notes: Optional[str] = None
    # Localization gap: English-only apps = opening for localized clones.
    language_codes: List[str] = field(default_factory=list)
    screenshot_count: int = 0
    ipad_screenshot_count: int = 0
    file_size_mb: Optional[float] = None
    minimum_os_version: Optional[str] = None
    content_rating: Optional[str] = None


@dataclass
class ReviewItem:
    review_id: str
    author: Optional[str]
    title: Optional[str]
    body: Optional[str]
    rating: Optional[int]
    version: Optional[str]
    updated: Optional[datetime] = None


@dataclass
class ItunesClient:
    country: str = "us"
    session: requests.Session = field(default_factory=requests.Session)

    def __post_init__(self) -> None:
        self.session.headers.update(HEADERS)

    # ---- low level -------------------------------------------------------
    @retry(
        retry=retry_if_exception_type((requests.RequestException, ItunesError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _get_json(self, url: str) -> Dict[str, Any]:
        resp = self.session.get(url, timeout=DEFAULT_TIMEOUT)
        if resp.status_code == 429:
            raise ItunesError("Rate limited (429)")
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError as exc:
            raise ItunesError(f"Non-JSON response from {url}") from exc

    # ---- charts ----------------------------------------------------------
    def top_chart(self, chart: str, genre_id: int, limit: int = 50) -> List[ChartEntry]:
        """Fetch a top chart for a genre. Reliable endpoint."""
        limit = max(1, min(limit, 200))
        url = f"{BASE}/{self.country}/rss/{chart}/limit={limit}/genre={genre_id}/json"
        try:
            data = self._get_json(url)
        except Exception as exc:  # noqa: BLE001 - never let one genre kill the run
            logger.warning("Chart fetch failed genre=%s chart=%s: %s", genre_id, chart, exc)
            return []

        entries_raw = (data.get("feed", {}) or {}).get("entry", []) or []
        # Apple returns a dict (not list) when there's exactly one entry.
        if isinstance(entries_raw, dict):
            entries_raw = [entries_raw]

        out: List[ChartEntry] = []
        for rank, e in enumerate(entries_raw, start=1):
            try:
                out.append(self._parse_chart_entry(e, genre_id, rank))
            except Exception as exc:  # noqa: BLE001
                logger.debug("Skip malformed chart entry: %s", exc)
        logger.info("Chart genre=%s chart=%s -> %d apps", genre_id, chart, len(out))
        return out

    @staticmethod
    def _parse_chart_entry(e: Dict[str, Any], genre_id: int, rank: int) -> ChartEntry:
        id_attr = (e.get("id", {}) or {}).get("attributes", {}) or {}
        app_id = int(id_attr.get("im:id"))
        name = (e.get("im:name", {}) or {}).get("label", "")
        artist = (e.get("im:artist", {}) or {}).get("label")
        price_obj = (e.get("im:price", {}) or {}).get("attributes", {}) or {}
        try:
            price = float(price_obj.get("amount", 0) or 0)
        except (TypeError, ValueError):
            price = 0.0
        currency = price_obj.get("currency")
        cat_attr = (e.get("category", {}) or {}).get("attributes", {}) or {}
        try:
            g = int(cat_attr.get("im:id")) if cat_attr.get("im:id") else genre_id
        except (TypeError, ValueError):
            g = genre_id
        link = (e.get("id", {}) or {}).get("label")
        images = e.get("im:image", []) or []
        icon = images[-1].get("label") if images else None
        return ChartEntry(
            app_id=app_id,
            name=name,
            developer=artist,
            genre_id=g,
            price=price,
            currency=currency,
            url=link,
            icon_url=icon,
            rank=rank,
        )

    # ---- metadata --------------------------------------------------------
    def lookup(self, app_ids: List[int]) -> Dict[int, AppMetadata]:
        """Batch lookup exact rating/version metadata. Reliable endpoint.

        iTunes Lookup accepts comma-separated ids (batch up to ~200).
        """
        result: Dict[int, AppMetadata] = {}
        for batch in _chunks(app_ids, 100):
            ids = ",".join(str(i) for i in batch)
            url = f"{BASE}/lookup?id={ids}&country={self.country}"
            try:
                data = self._get_json(url)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Lookup batch failed: %s", exc)
                continue
            for r in data.get("results", []) or []:
                meta = self._parse_lookup(r)
                if meta:
                    result[meta.app_id] = meta
        return result

    @staticmethod
    def _parse_lookup(r: Dict[str, Any]) -> Optional[AppMetadata]:
        try:
            app_id = int(r.get("trackId"))
        except (TypeError, ValueError):
            return None
        return AppMetadata(
            app_id=app_id,
            name=r.get("trackName", ""),
            developer=r.get("artistName"),
            genre_id=int(r["primaryGenreId"]) if r.get("primaryGenreId") else None,
            rating_avg=r.get("averageUserRating"),
            rating_count=r.get("userRatingCount"),
            version=r.get("version"),
            price=float(r.get("price", 0) or 0),
            currency=r.get("currency"),
            description=r.get("description"),
            url=r.get("trackViewUrl"),
            icon_url=r.get("artworkUrl100"),
            release_date=_parse_apple_date(r.get("releaseDate")),
            current_version_release_date=_parse_apple_date(
                r.get("currentVersionReleaseDate")
            ),
            artist_id=_to_int(r.get("artistId")),
            genre_ids=[g for g in (_to_int(x) for x in r.get("genreIds", []) or []) if g],
            rating_avg_current=r.get("averageUserRatingForCurrentVersion"),
            rating_count_current=_to_int(r.get("userRatingCountForCurrentVersion")),
            release_notes=r.get("releaseNotes"),
            language_codes=[str(c) for c in r.get("languageCodesISO2A", []) or []],
            screenshot_count=len(r.get("screenshotUrls", []) or []),
            ipad_screenshot_count=len(r.get("ipadScreenshotUrls", []) or []),
            file_size_mb=_to_mb(r.get("fileSizeBytes")),
            minimum_os_version=r.get("minimumOsVersion"),
            content_rating=r.get("contentAdvisoryRating") or r.get("trackContentRating"),
        )

    # ---- search (micro-niche discovery) ---------------------------------
    def search(
        self, term: str, limit: int = 50, genre_id: Optional[int] = None
    ) -> List[AppMetadata]:
        """iTunes Search API - free, reliable, returns full metadata + ratings.

        This is the engine of micro-niche discovery: it returns the apps that
        actually compete for a specific search term (a candidate niche), each
        with its exact rating avg/count, so we can score the niche directly.
        `genre_id` restricts results to one category, so a keyword analysed in
        the context of e.g. Health & Fitness is not polluted by unrelated apps.
        """
        from urllib.parse import quote_plus

        limit = max(1, min(limit, 200))
        url = (
            f"{BASE}/search?term={quote_plus(term)}&country={self.country}"
            f"&entity=software&limit={limit}"
        )
        if genre_id:
            url += f"&genreId={int(genre_id)}"
        try:
            data = self._get_json(url)
        except Exception as exc:  # noqa: BLE001 - one term must not kill a batch
            logger.warning("Search failed term=%r: %s", term, exc)
            return []
        out: List[AppMetadata] = []
        for r in data.get("results", []) or []:
            meta = self._parse_lookup(r)
            if meta:
                out.append(meta)
        logger.info("Search %r -> %d apps", term, len(out))
        return out

    # ---- search hints (free search-interest proxy) ----------------------
    def search_hints(self, term: str) -> List[str]:
        """Apple's autocomplete suggestions, ordered ~by search popularity.

        Free, keyless. Used as a proxy for "do people actually search this?".
        Returns a list of suggested terms (may be empty).
        """
        import plistlib
        from urllib.parse import quote

        url = (
            "https://search.itunes.apple.com/WebObjects/MZSearchHints.woa/wa/"
            f"hints?clientApplication=Software&term={quote(term)}"
        )
        try:
            resp = self.session.get(
                url, timeout=DEFAULT_TIMEOUT,
                headers={"X-Apple-Store-Front": "143441-1,29"},
            )
            resp.raise_for_status()
            data = plistlib.loads(resp.content)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Search hints failed term=%r: %s", term, exc)
            return []
        hints = data.get("hints", []) if isinstance(data, dict) else []
        out: List[str] = []
        for h in hints:
            if isinstance(h, dict) and h.get("term"):
                out.append(str(h["term"]))
            elif isinstance(h, str):
                out.append(h)
        return out

    # ---- reviews (best effort) ------------------------------------------
    def reviews(self, app_id: int, pages: int = 5) -> List[ReviewItem]:
        """Fetch recent reviews. BEST EFFORT - returns [] on empty feed."""
        out: List[ReviewItem] = []
        for page in range(1, pages + 1):
            url = (
                f"{BASE}/{self.country}/rss/customerreviews/"
                f"id={app_id}/sortBy=mostRecent/page={page}/json"
            )
            try:
                data = self._get_json(url)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Reviews fetch failed app=%s page=%s: %s", app_id, page, exc)
                break

            entries = (data.get("feed", {}) or {}).get("entry", []) or []
            if isinstance(entries, dict):
                entries = [entries]
            # First entry can be app metadata (has im:name but no author/content).
            page_reviews = [e for e in entries if e.get("author") and e.get("content")]
            if not page_reviews:
                break
            for e in page_reviews:
                item = self._parse_review(e)
                if item:
                    out.append(item)
        if not out:
            logger.debug("No reviews returned for app=%s (feed empty/deprecated)", app_id)
        return out

    @staticmethod
    def _parse_review(e: Dict[str, Any]) -> Optional[ReviewItem]:
        try:
            rid = (e.get("id", {}) or {}).get("label")
            if not rid:
                return None
            rating_raw = (e.get("im:rating", {}) or {}).get("label")
            rating = int(rating_raw) if rating_raw else None
            author = (e.get("author", {}) or {}).get("name", {}).get("label")
            title = (e.get("title", {}) or {}).get("label")
            body = (e.get("content", {}) or {}).get("label")
            version = (e.get("im:version", {}) or {}).get("label")
            updated = _parse_apple_date((e.get("updated", {}) or {}).get("label"))
            return ReviewItem(
                review_id=str(rid),
                author=author,
                title=title,
                body=body,
                rating=rating,
                version=version,
                updated=updated,
            )
        except Exception:  # noqa: BLE001
            return None


def _chunks(items: List[int], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _to_mb(value: Any) -> Optional[float]:
    try:
        return round(int(value) / (1024 * 1024), 1) if value else None
    except (TypeError, ValueError):
        return None


def _parse_apple_date(value: Optional[str]) -> Optional[datetime]:
    """Parse Apple ISO timestamps like '2020-05-01T07:00:00Z' -> naive UTC."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.replace(tzinfo=None)
    except (ValueError, TypeError):
        return None
