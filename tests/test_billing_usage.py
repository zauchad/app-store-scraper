"""Usage quota tests."""
from __future__ import annotations

import uuid

from src.billing.credits import PRO_PLAN, ensure_user, set_user_plan
from src.billing.usage import can_run_keyword_scan, record_keyword_scan


def test_free_user_scan_limit(billing_env):
    uid = f"usage-{uuid.uuid4().hex[:8]}"
    ensure_user(uid, f"{uid}@test.com")
    limit = billing_env.free_daily_keyword_scans
    for _ in range(limit):
        ok, _ = can_run_keyword_scan(uid)
        assert ok
        record_keyword_scan(uid)
    ok, msg = can_run_keyword_scan(uid)
    assert not ok
    assert "limit" in msg.lower() or "Limit" in msg


def test_pro_user_unlimited_scans(billing_env):
    uid = f"pro-{uuid.uuid4().hex[:8]}"
    ensure_user(uid, f"{uid}@test.com")
    set_user_plan(uid, PRO_PLAN, reason="test")
    for _ in range(10):
        ok, _ = can_run_keyword_scan(uid, use_ai=True)
        assert ok
