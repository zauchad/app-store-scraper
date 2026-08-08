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


class AsaVolumeProvider(SearchVolumeProvider):
    """OFFICIAL Apple Ads search popularity (5-100 scale) -> 0..1.

    Cost: FREE - requires only an Apple Ads account (no ad spend) with an API
    user (Account Settings -> API): you upload a public key and get clientId /
    teamId / keyId. OAuth2 client_credentials with an ES256 client-secret JWT.

    Since Oct 2025 Apple returns popularity only for terms with SP >= 35;
    anything below (and any API hiccup) silently falls back to the free
    autocomplete proxy, so scoring never breaks.

    The popularity endpoint is configured via ASA_POPULARITY_URL (+ optional
    ASA_POPULARITY_BODY for POST) with {term}/{country} placeholders, because
    Apple has been reshaping this surface; parsing is defensive and accepts
    any `popularity`/`searchPopularity` field in the response.
    """

    name = "asa"
    TOKEN_URL = "https://appleid.apple.com/auth/oauth2/token"
    AUDIENCE = "https://appleid.apple.com"

    def __init__(self, fallback: SearchVolumeProvider) -> None:
        import requests

        missing = [
            k for k, v in {
                "ASA_CLIENT_ID": settings.asa_client_id,
                "ASA_TEAM_ID": settings.asa_team_id,
                "ASA_KEY_ID": settings.asa_key_id,
                "ASA_PRIVATE_KEY": settings.asa_private_key,
                "ASA_ORG_ID": settings.asa_org_id,
                "ASA_POPULARITY_URL": settings.asa_popularity_url,
            }.items() if not v
        ]
        if missing:
            raise ValueError(f"Apple Ads provider: brak konfiguracji {missing}")
        self._fallback = fallback
        self._session = requests.Session()
        self._token: Optional[str] = None
        self._token_exp: float = 0.0

    def _private_key_pem(self) -> str:
        val = settings.asa_private_key
        if "BEGIN" in val:
            return val.replace("\\n", "\n")
        from pathlib import Path

        return Path(val).read_text()

    def _client_secret(self) -> str:
        import time

        try:
            import jwt  # PyJWT + cryptography (see requirements.txt)
        except ImportError as exc:
            raise RuntimeError(
                "Provider ASA wymaga: pip install PyJWT cryptography"
            ) from exc
        now = int(time.time())
        return jwt.encode(
            {
                "sub": settings.asa_client_id,
                "aud": self.AUDIENCE,
                "iat": now,
                "exp": now + 3600,
                "iss": settings.asa_team_id,
            },
            self._private_key_pem(),
            algorithm="ES256",
            headers={"kid": settings.asa_key_id},
        )

    def _get_token(self) -> str:
        import time

        if self._token and time.time() < self._token_exp - 300:
            return self._token
        resp = self._session.post(
            self.TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.asa_client_id,
                "client_secret": self._client_secret(),
                "scope": "searchadsorg",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_exp = time.time() + int(data.get("expires_in", 3600))
        return self._token

    @staticmethod
    def _extract_popularity(node, term: str, best: Optional[float] = None):
        """Walk any JSON shape; prefer the entry matching `term` exactly."""
        if isinstance(node, dict):
            text = str(node.get("text") or node.get("keyword") or "").lower()
            for key in ("searchPopularity", "popularity", "searchPopularityScore"):
                val = node.get(key)
                if isinstance(val, (int, float)):
                    if text == term:
                        return float(val), True
                    if best is None or val > best:
                        best = float(val)
            for v in node.values():
                found = AsaVolumeProvider._extract_popularity(v, term, best)
                if isinstance(found, tuple):
                    return found
                best = found if found is not None else best
        elif isinstance(node, list):
            for v in node:
                found = AsaVolumeProvider._extract_popularity(v, term, best)
                if isinstance(found, tuple):
                    return found
                best = found if found is not None else best
        return best

    def interest(self, term: str) -> Optional[float]:
        t = term.strip().lower()
        try:
            from urllib.parse import quote_plus

            headers = {
                "Authorization": f"Bearer {self._get_token()}",
                "X-AP-Context": f"orgId={settings.asa_org_id}",
                "Content-Type": "application/json",
            }
            url = settings.asa_popularity_url.format(
                term=quote_plus(t), country=settings.store_country.upper()
            )
            if settings.asa_popularity_body:
                body = settings.asa_popularity_body.replace("{term}", t).replace(
                    "{country}", settings.store_country.upper()
                )
                resp = self._session.post(url, data=body, headers=headers, timeout=20)
            else:
                resp = self._session.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            found = self._extract_popularity(resp.json(), t)
            pop = found[0] if isinstance(found, tuple) else found
            if pop is not None and pop > 0:
                # 5-100 -> 0.05..1.0 (same scale the proxy already uses).
                return round(min(max(pop / 100.0, 0.05), 1.0), 3)
        except Exception as exc:  # noqa: BLE001 - never break scoring
            logger.warning("ASA popularity failed for %r (%s) -> proxy fallback",
                           t, exc)
        return self._fallback.interest(term)


def get_volume_provider() -> SearchVolumeProvider:
    provider = settings.volume_provider.lower()
    if provider == "none":
        return NullVolumeProvider()
    proxy = ProxyVolumeProvider(country=settings.store_country)
    if provider == "asa":
        try:
            return AsaVolumeProvider(fallback=proxy)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ASA provider niedostępny (%s) -> używam proxy", exc)
    return proxy
