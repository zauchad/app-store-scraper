"""Standalone FastAPI server for Lemon Squeezy webhooks.

Streamlit Cloud cannot receive inbound webhooks, so deploy this on Railway,
Fly.io, Render, etc. and point Lemon Squeezy at POST /webhooks/lemon-squeezy.

Usage:
    python run.py webhook-server
    # or: uvicorn billing.webhook_server:app --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

import json

from fastapi import FastAPI, Header, HTTPException, Request

from src.billing.lemon_squeezy import handle_webhook, verify_signature
from src.billing.webhook_notify import log_webhook_failure
from src.db.session import init_db
from src.logging_config import get_logger

logger = get_logger(__name__)

app = FastAPI(title="Market Intel Billing Webhooks")


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhooks/lemon-squeezy")
async def lemon_squeezy_webhook(
    request: Request,
    x_signature: str = Header(default="", alias="X-Signature"),
) -> dict:
    raw = await request.body()
    if not verify_signature(raw, x_signature):
        logger.warning("Invalid Lemon Squeezy signature")
        log_webhook_failure(event_name="signature", error="invalid signature")
        raise HTTPException(status_code=401, detail="invalid signature")

    try:
        payload = json.loads(raw.decode())
    except json.JSONDecodeError as exc:
        log_webhook_failure(event_name="parse", error=str(exc))
        raise HTTPException(status_code=400, detail="invalid json") from exc

    event_name = str((payload.get("meta") or {}).get("event_name") or "unknown")
    try:
        result = handle_webhook(payload)
    except Exception as exc:  # noqa: BLE001
        log_webhook_failure(event_name=event_name, error=str(exc), payload=payload)
        raise HTTPException(status_code=500, detail="processing failed") from exc

    if not result.get("ok"):
        log_webhook_failure(
            event_name=event_name,
            error=str(result.get("error", "failed")),
            payload=payload,
        )
        raise HTTPException(status_code=400, detail=result.get("error", "failed"))
    return result
