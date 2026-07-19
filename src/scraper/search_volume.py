"""Pluggable search-volume (search-interest) providers.

Honest framing: TRUE search volume is a paid signal (Apple Search Ads
popularity 5-100, or ASO tools like AppTweak/Sensor Tower). We isolate it behind
a provider so you can plug a paid source later without touching the scorer.

Default = ProxyVolumeProvider: a FREE proxy built from Apple's autocomplete
("search hints"), which Apple orders roughly by popularity. It answers "do
people actually search this term, and is it a popular stem?" - not an exact
volume, but a strong 0..1 relative signal that meaningfully improves demand
estimation for micro-niches.

To upgrade to real volume: implement `interest()` in a new provider (e.g. Apple
Search Ads) and return it from `get_volume_provider()`.
"""
from __future__ import annotations

from typing import Optional

from src.config import settings
from src.logging_config import get_logger
from src.scraper.itunes_client import ItunesClient

logger = get_logger(__name__)


class SearchVolumeProvider:
    name = "base"

    def interest(self, term: str) -> Optional[float]:
        """Return 0..1 search interest, or None if unknown (scorer falls back)."""
        raise NotImplementedError


class NullVolumeProvider(SearchVolumeProvider):
    name = "none"

    def interest(self, term: str) -> Optional[float]:
        return None


class ProxyVolumeProvider(SearchVolumeProvider):
    """Free proxy from App Store autocomplete ordering."""

    name = "proxy"

    def __init__(self, country: str) -> None:
        self._client = ItunesClient(country=country)

    @staticmethod
    def _score_from(hints: list, target: str) -> float:
        if not hints:
            return 0.0
        hl = [h.lower() for h in hints]
        # How "extendable" / popular the stem is (many completions of it).
        starts = sum(1 for h in hl if h.startswith(target))
        score = min(starts / 6.0, 1.0)
        # If Apple autocompletes to the exact term, weight by its rank.
        if target in hl:
            rank = hl.index(target)
            score = max(score, 1.0 - 0.4 * rank / max(1, len(hl) - 1))
        return score

    def interest(self, term: str) -> Optional[float]:
        t = term.strip().lower()
        words = t.split()
        hints_full = self._client.search_hints(t)
        score = self._score_from(hints_full, t)

        # Long-tail fairness: ask the "head" of the phrase and see whether Apple
        # suggests this exact refinement (means people search the long-tail too).
        if len(words) >= 2:
            head_hints = [h.lower() for h in self._client.search_hints(" ".join(words[:-1]))]
            if t in head_hints:
                rank = head_hints.index(t)
                score = max(score, 0.85 - 0.4 * rank / max(1, len(head_hints) - 1))
            elif any(all(w in h for w in words) for h in head_hints):
                score = max(score, 0.4)
            elif any(words[-1] in h for h in head_hints):
                score = max(score, 0.2)

        if not hints_full and score == 0.0:
            return 0.05
        return round(min(max(score, 0.05), 1.0), 3)


def get_volume_provider() -> SearchVolumeProvider:
    provider = settings.volume_provider.lower()
    if provider == "none":
        return NullVolumeProvider()
    return ProxyVolumeProvider(country=settings.store_country)
