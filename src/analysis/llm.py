"""Provider-agnostic LLM layer.

Why an abstraction: today Gemini's free tier is the fastest/cheapest way to
synthesise thousands of reviews. Tomorrow you may switch to OpenAI/Anthropic.
Callers depend on `LLMClient`, never on a specific SDK, so swapping providers is
a one-line config change (LLM_PROVIDER).

The client returns strict JSON so downstream code and the dashboard can render
structured business conclusions (not free-form prose).
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, Optional, Protocol

from src.config import settings
from src.logging_config import get_logger

logger = get_logger(__name__)


class LLMError(Exception):
    pass


class LLMQuotaError(LLMError):
    """Raised when the *daily* free-tier quota is exhausted (retry won't help)."""


# Circuit breaker: once the daily quota is hit, stop hammering the API for the
# rest of the process (callers check is_quota_exhausted() to bail out early).
_quota_exhausted = False
_last_call_ts = 0.0


def is_quota_exhausted() -> bool:
    return _quota_exhausted


def _throttle() -> None:
    """Space out calls to respect per-minute rate limits."""
    global _last_call_ts
    interval = settings.llm_min_interval_seconds
    if interval > 0:
        wait = interval - (time.time() - _last_call_ts)
        if wait > 0:
            time.sleep(wait)
    _last_call_ts = time.time()


def _parse_retry_delay(msg: str) -> Optional[float]:
    m = re.search(r"ret[rR]y(?:Delay)?['\":\s]+(?:in\s+)?([\d.]+)s", msg)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


class LLMClient(Protocol):
    model_name: str

    def generate_json(self, prompt: str, system: Optional[str] = None) -> Dict[str, Any]:
        ...


def _is_daily_quota(msg: str) -> bool:
    return ("PerDay" in msg) or ("per_day" in msg.lower())


class GeminiClient:
    """Gemini via google-genai, with a rotating pool of API keys.

    When one key hits its DAILY free-tier quota (429 PerDay), we mark it spent
    and rotate to the next key, so several keys (ideally from separate Google
    Cloud projects) multiply the effective daily capacity. Only when EVERY key is
    exhausted do we trip the global circuit breaker.
    """

    def __init__(self, api_keys, model: str) -> None:
        try:
            from google import genai  # imported lazily so the app runs without it
        except ImportError as exc:  # pragma: no cover
            raise LLMError(
                "google-genai not installed. Run: pip install google-genai"
            ) from exc
        self._genai = genai
        self._keys = list(api_keys)
        if not self._keys:
            raise LLMError("No Gemini API keys configured.")
        self.model_name = model
        self._clients: Dict[int, Any] = {}
        self._spent: set = set()  # indices whose daily quota is exhausted
        self._idx = 0

    def _client_for(self, idx: int):
        if idx not in self._clients:
            self._clients[idx] = self._genai.Client(api_key=self._keys[idx])
        return self._clients[idx]

    def _next_available(self) -> Optional[int]:
        for _ in range(len(self._keys)):
            if self._idx not in self._spent:
                return self._idx
            self._idx = (self._idx + 1) % len(self._keys)
        return None

    def generate_json(self, prompt: str, system: Optional[str] = None) -> Dict[str, Any]:
        global _quota_exhausted
        from google.genai import types

        if _quota_exhausted:
            raise LLMQuotaError("Daily LLM quota already exhausted this run.")

        contents = prompt if system is None else f"{system}\n\n{prompt}"
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.3,
        )
        retries = max(0, settings.llm_max_retries)

        # Try each still-available key; rotate on daily-quota exhaustion.
        while True:
            idx = self._next_available()
            if idx is None:
                _quota_exhausted = True
                raise LLMQuotaError(
                    f"All {len(self._keys)} Gemini key(s) hit their daily quota. "
                    "Add more keys (GEMINI_API_KEYS), use a higher-limit model, "
                    "or run LLM steps less often."
                )
            client = self._client_for(idx)
            key_label = f"key#{idx + 1}/{len(self._keys)}"
            try:
                return self._call_with_retries(client, contents, config, retries, key_label)
            except LLMQuotaError:
                # This key is spent for today -> mark and try the next one.
                self._spent.add(idx)
                self._idx = (self._idx + 1) % len(self._keys)
                logger.warning(
                    "%s daily quota exhausted; rotating to next key.", key_label
                )
                continue

    def _call_with_retries(self, client, contents, config, retries, key_label) -> Dict[str, Any]:
        for attempt in range(retries + 1):
            _throttle()
            try:
                resp = client.models.generate_content(
                    model=self.model_name, contents=contents, config=config
                )
                return _safe_json_loads((resp.text or "").strip())
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                is_429 = "429" in msg or "RESOURCE_EXHAUSTED" in msg
                if is_429 and _is_daily_quota(msg):
                    raise LLMQuotaError(f"{key_label} daily quota exhausted") from exc
                if is_429 and attempt < retries:
                    delay = _parse_retry_delay(msg) or (2 ** (attempt + 1))
                    logger.warning(
                        "LLM rate-limited (429) on %s; retrying in %.0fs [%d/%d]",
                        key_label, min(delay, 60), attempt + 1, retries,
                    )
                    time.sleep(min(delay, 60))
                    continue
                raise LLMError(f"Gemini call failed: {exc}") from exc
        raise LLMError("Gemini call failed after retries")


def _safe_json_loads(text: str) -> Dict[str, Any]:
    """Parse JSON, tolerating code fences or stray prose around it."""
    if not text:
        raise LLMError("Empty LLM response")
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise LLMError("Could not parse JSON from LLM response")


def get_llm_client() -> Optional[LLMClient]:
    """Factory. Returns None if no key configured (dashboard degrades gracefully)."""
    if not settings.llm_enabled:
        logger.warning("LLM disabled: no GEMINI_API_KEY set.")
        return None
    provider = settings.llm_provider.lower()
    if provider == "gemini":
        keys = settings.gemini_key_list
        logger.info("LLM: Gemini with %d key(s) in pool.", len(keys))
        return GeminiClient(keys, settings.gemini_model)
    raise LLMError(f"Unknown LLM_PROVIDER: {provider}")
