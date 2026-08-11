
def test_order_refunded_claws_back_credits(billing_env):
    import uuid

    from src.billing.credits import ensure_user, get_user, grant_credits
    from src.billing.lemon_squeezy import handle_webhook

    uid = f"ref-{uuid.uuid4().hex[:8]}"
    ensure_user(uid, f"{uid}@test.com")
    order_id = "ord-refund-1"
    grant_payload = {
        "meta": {
            "event_name": "order_created",
            "custom_data": {"user_id": uid, "credits": 5},
        },
        "data": {
            "id": order_id,
            "attributes": {
                "user_email": f"{uid}@test.com",
                "first_order_item": {"variant_id": 0},
            },
        },
    }
    r1 = handle_webhook(grant_payload)
    assert r1.get("credits") == 5
    assert get_user(uid).credits_balance == 5

    refund_payload = {
        "meta": {
            "event_name": "order_refunded",
            "custom_data": {"user_id": uid},
        },
        "data": {"id": order_id, "attributes": {}},
    }
    r2 = handle_webhook(refund_payload)
    assert r2.get("action") == "refund"
    assert r2.get("clawed_back") == 5
    assert get_user(uid).credits_balance == 0
