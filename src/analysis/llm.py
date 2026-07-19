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
from typing import Any, Dict, Optional, Protocol

from src.config import settings
from src.logging_config import get_logger

logger = get_logger(__name__)


class LLMError(Exception):
    pass


class LLMClient(Protocol):
    model_name: str

    def generate_json(self, prompt: str, system: Optional[str] = None) -> Dict[str, Any]:
        ...


class GeminiClient:
    """Gemini implementation using the google-genai SDK."""

    def __init__(self, api_key: str, model: str) -> None:
        try:
            from google import genai  # imported lazily so the app runs without it
        except ImportError as exc:  # pragma: no cover
            raise LLMError(
                "google-genai not installed. Run: pip install google-genai"
            ) from exc
        self._genai = genai
        self._client = genai.Client(api_key=api_key)
        self.model_name = model

    def generate_json(self, prompt: str, system: Optional[str] = None) -> Dict[str, Any]:
        from google.genai import types

        contents = prompt if system is None else f"{system}\n\n{prompt}"
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.3,
        )
        try:
            resp = self._client.models.generate_content(
                model=self.model_name, contents=contents, config=config
            )
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Gemini call failed: {exc}") from exc

        text = (resp.text or "").strip()
        return _safe_json_loads(text)


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
        return GeminiClient(settings.gemini_api_key, settings.gemini_model)
    raise LLMError(f"Unknown LLM_PROVIDER: {provider}")
