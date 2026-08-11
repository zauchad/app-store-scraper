"""Daily usage quotas and keyword-scan gating."""
from __future__ import annotations

from datetime import date
from typing import Optional, Tuple

from sqlalchemy import select

from src.billing.credits import has_pro_access, monetization_active
from src.config import settings
from src.db.models import DailyUsage
from src.db.session import session_scope


def _today() -> str:
    return date.today().isoformat()


def _count_today(user_id: str) -> int:
    with session_scope() as session:
        row = session.execute(
            select(DailyUsage.keyword_scans).where(
                DailyUsage.user_id == user_id,
                DailyUsage.usage_date == _today(),
            )
        ).scalar_one_or_none()
        return int(row or 0)


def can_run_keyword_scan(user_id: Optional[str], *, use_ai: bool = False) -> Tuple[bool, str]:
    if not monetization_active():
        return True, ""
    if not user_id:
        return False, "🔒 Zaloguj się w panelu bocznym, aby analizować mikro-nisze."
    if use_ai and not has_pro_access(user_id):
        return (
            False,
            "🔒 Generator AI mikro-nisz jest dostępny w planie **Pro** ($39/mies.).",
        )
    if has_pro_access(user_id):
        return True, ""
    limit = settings.free_daily_keyword_scans
    used = _count_today(user_id)
    if used >= limit:
        return (
            False,
            f"🔒 Limit **{limit}** skanów/dzień na planie Free. "
            "Wykup **Pro** dla nielimitowanych analiz lub wróć jutro.",
        )
    return True, ""


def record_keyword_scan(user_id: str) -> None:
    if not monetization_active() or has_pro_access(user_id):
        return
    today = _today()
    with session_scope() as session:
        row = session.execute(
            select(DailyUsage).where(
                DailyUsage.user_id == user_id,
                DailyUsage.usage_date == today,
            )
        ).scalar_one_or_none()
        if row is None:
            session.add(DailyUsage(user_id=user_id, usage_date=today, keyword_scans=1))
        else:
            row.keyword_scans += 1


def keyword_scans_remaining(user_id: Optional[str]) -> Optional[int]:
    if not monetization_active() or not user_id:
        return None
    if has_pro_access(user_id):
        return None  # unlimited
    return max(0, settings.free_daily_keyword_scans - _count_today(user_id))
