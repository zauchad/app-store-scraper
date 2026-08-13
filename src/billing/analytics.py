"""Funnel tracking: where buyers appear and where they drop off.

Fire-and-forget by design — a tracking failure must never break a page render or
a payment webhook. Read it back with ``python run.py funnel``.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select

from src.db.models import FunnelEvent, User
from src.db.session import session_scope
from src.logging_config import get_logger

logger = get_logger(__name__)

# Ordered funnel steps — the report walks them top to bottom.
LANDING_VIEW = "landing_view"
SIGNUP = "signup"
LOGIN = "login"
GATE_VIEW = "gate_view"
CHECKOUT_VIEW = "checkout_view"
PURCHASE = "purchase"
UNLOCK = "unlock"
PRO_ACTIVATE = "pro_activate"
REFUND = "refund"

FUNNEL_STEPS: Tuple[str, ...] = (
    LANDING_VIEW,
    SIGNUP,
    LOGIN,
    GATE_VIEW,
    CHECKOUT_VIEW,
    PURCHASE,
    UNLOCK,
    PRO_ACTIVATE,
    REFUND,
)

STEP_LABELS: Dict[str, str] = {
    LANDING_VIEW: "Landing (unikalne sesje)",
    SIGNUP: "Rejestracje",
    LOGIN: "Logowania",
    GATE_VIEW: "Zobaczyli paywall",
    CHECKOUT_VIEW: "Zobaczyli cennik/checkout",
    PURCHASE: "Zakupy (webhook)",
    UNLOCK: "Odblokowane nisze",
    PRO_ACTIVATE: "Aktywacje Pro",
    REFUND: "Zwroty",
}


def track(event: str, *, user_id: Optional[str] = None, detail: Optional[str] = None) -> None:
    """Record one funnel step. Never raises."""
    try:
        with session_scope() as session:
            session.add(
                FunnelEvent(
                    event=event[:32],
                    user_id=(user_id or None),
                    detail=(detail[:128] if detail else None),
                )
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Funnel tracking failed for %s: %s", event, exc)


def counts_since(days: int = 30) -> Dict[str, Tuple[int, int]]:
    """Per step: (total events, distinct users)."""
    since = datetime.utcnow() - timedelta(days=days)
    out: Dict[str, Tuple[int, int]] = {}
    with session_scope() as session:
        rows = session.execute(
            select(
                FunnelEvent.event,
                func.count(FunnelEvent.id),
                func.count(func.distinct(FunnelEvent.user_id)),
            )
            .where(FunnelEvent.created_at >= since)
            .group_by(FunnelEvent.event)
        ).all()
    for event, total, users in rows:
        out[str(event)] = (int(total or 0), int(users or 0))
    return out


def paying_users() -> int:
    with session_scope() as session:
        return int(
            session.execute(
                select(func.count(User.id)).where(User.credits_balance > 0)
            ).scalar_one()
            or 0
        )


def format_funnel_report(days: int = 30) -> str:
    """Plain-text funnel for the CLI."""
    data = counts_since(days)
    lines: List[str] = [f"Funnel — ostatnie {days} dni", "=" * 34]

    signups = data.get(SIGNUP, (0, 0))[0]
    purchases = data.get(PURCHASE, (0, 0))[0]

    for step in FUNNEL_STEPS:
        total, users = data.get(step, (0, 0))
        label = STEP_LABELS.get(step, step)
        lines.append(f"{label:<32} {total:>6}  (użytkowników: {users})")

    lines.append("-" * 34)
    if signups:
        lines.append(f"Konwersja rejestracja → zakup: {purchases / signups:.1%}")
    else:
        lines.append("Konwersja rejestracja → zakup: brak rejestracji w okresie")
    gate = data.get(GATE_VIEW, (0, 0))[1]
    if gate:
        buyers = data.get(PURCHASE, (0, 0))[1]
        lines.append(f"Konwersja paywall → zakup:     {buyers / gate:.1%}")
    return "\n".join(lines)
