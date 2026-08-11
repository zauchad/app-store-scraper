"""Webhook failure logging and optional Slack alert."""
from __future__ import annotations

import json
from typing import Any, Optional

from src.config import settings
from src.db.models import WebhookFailure
from src.db.session import session_scope
from src.logging_config import get_logger

logger = get_logger(__name__)


def log_webhook_failure(
    *,
    event_name: str,
    error: str,
    payload: Optional[dict[str, Any]] = None,
) -> None:
    preview = ""
    if payload is not None:
        try:
            preview = json.dumps(payload, default=str)[:1000]
        except Exception:  # noqa: BLE001
            preview = str(payload)[:1000]

    with session_scope() as session:
        session.add(
            WebhookFailure(
                event_name=event_name[:64],
                error_message=error[:512],
                payload_preview=preview or None,
            )
        )

    logger.error("Webhook failure [%s]: %s", event_name, error)

    url = settings.slack_webhook_url.strip()
    if not url:
        return
    try:
        import requests

        text = f":warning: *Billing webhook failed*\n• Event: `{event_name}`\n• Error: {error[:200]}"
        requests.post(url, json={"text": text}, timeout=10)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not send Slack webhook alert: %s", exc)
