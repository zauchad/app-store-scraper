"""Digest delivery - close the loop: the system reports to YOU.

The daily cron already computes everything; without delivery the insights die
in a .md file nobody opens. Two zero/low-cost channels, both optional:

  * Slack  - incoming webhook (free): SLACK_WEBHOOK_URL
  * E-mail - any SMTP (Gmail app-password works): SMTP_HOST/PORT/USER/PASSWORD
             + EMAIL_FROM + EMAIL_TO (comma-separated for many recipients)

Configure one, both, or none - `send_digest` sends wherever it can and never
raises: a failed notification must not fail the daily pipeline.
"""
from __future__ import annotations

import re
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict

import requests

from src.config import settings
from src.logging_config import get_logger

logger = get_logger(__name__)

# Slack hard-limits a text block; stay well under it and chunk long digests.
SLACK_CHUNK = 3500


def slack_configured() -> bool:
    return bool(settings.slack_webhook_url)


def email_configured() -> bool:
    return bool(
        settings.smtp_host and settings.email_from and settings.email_to
    )


def notify_configured() -> bool:
    return slack_configured() or email_configured()


def _md_to_slack(md: str) -> str:
    """Best-effort Markdown -> Slack mrkdwn (bold + headers)."""
    out = []
    for line in md.splitlines():
        if line.startswith("#"):
            line = "*" + line.lstrip("# ").strip() + "*"
        line = re.sub(r"\*\*(.+?)\*\*", r"*\1*", line)
        out.append(line)
    return "\n".join(out)


def _send_slack(md: str) -> bool:
    text = _md_to_slack(md)
    chunks = [text[i:i + SLACK_CHUNK] for i in range(0, len(text), SLACK_CHUNK)]
    try:
        for chunk in chunks:
            resp = requests.post(
                settings.slack_webhook_url, json={"text": chunk}, timeout=15
            )
            resp.raise_for_status()
        logger.info("Digest sent to Slack (%d chunk(s))", len(chunks))
        return True
    except Exception as exc:  # noqa: BLE001 - delivery must never kill the cron
        logger.warning("Slack delivery failed: %s", exc)
        return False


def _send_email(md: str) -> bool:
    recipients = [a.strip() for a in settings.email_to.split(",") if a.strip()]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📡 Market Intel — digest {datetime.now():%Y-%m-%d}"
    msg["From"] = settings.email_from
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(md, "plain", "utf-8"))
    # Monospace HTML keeps the Markdown layout readable in every client
    # without pulling in a Markdown->HTML dependency.
    msg.attach(MIMEText(
        f"<pre style='font-family:Menlo,monospace;font-size:13px'>{md}</pre>",
        "html", "utf-8",
    ))
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
            s.ehlo()
            if settings.smtp_port != 25:
                s.starttls()
                s.ehlo()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.sendmail(settings.email_from, recipients, msg.as_string())
        logger.info("Digest e-mailed to %s", recipients)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("E-mail delivery failed: %s", exc)
        return False


def send_digest(md: str) -> Dict[str, bool]:
    """Send the digest to every configured channel. Returns per-channel status."""
    status: Dict[str, bool] = {}
    if slack_configured():
        status["slack"] = _send_slack(md)
    if email_configured():
        status["email"] = _send_email(md)
    if not status:
        logger.info(
            "Digest delivery skipped - no channel configured "
            "(set SLACK_WEBHOOK_URL and/or SMTP_* + EMAIL_* in .env)."
        )
    return status
