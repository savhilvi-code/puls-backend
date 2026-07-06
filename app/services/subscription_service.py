from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.database.supabase import get_supabase_client

FREE_LIMIT = 10
PAID_LIMIT = 100


def _rows(response) -> list[dict]:
    return getattr(response, "data", []) or []


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _free_period_end() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=3650)).isoformat()


def _normalize_subscription(row: dict | None) -> dict[str, Any]:
    row = row or {}
    plan = str(row.get("plan") or "free")
    requests_limit = int(row.get("requests_limit") or (PAID_LIMIT if plan == "paid" else FREE_LIMIT))
    requests_used = int(row.get("requests_used") or 0)
    remaining = max(requests_limit - requests_used, 0)
    return {
        "id": row.get("id"),
        "user_id": row.get("user_id"),
        "plan": plan,
        "status": str(row.get("status") or "active"),
        "provider": row.get("provider"),
        "provider_customer_id": row.get("provider_customer_id"),
        "provider_subscription_id": row.get("provider_subscription_id"),
        "requests_limit": requests_limit,
        "requests_used": requests_used,
        "remaining": remaining,
        "current_period_start": row.get("current_period_start"),
        "current_period_end": row.get("current_period_end"),
    }


def get_active_subscription(*, user_id: int | None) -> dict[str, Any] | None:
    if user_id is None:
        return None
    response = (
        get_supabase_client()
        .table("subscriptions")
        .select("*")
        .eq("user_id", user_id)
        .in_("status", ["active", "trialing", "inactive"])
        .order("updated_at", desc=True)
        .limit(5)
        .execute()
    )
    rows = _rows(response)
    if not rows:
        return None
    for row in rows:
        if str(row.get("status") or "").lower() in {"active", "trialing"}:
            return _normalize_subscription(row)
    return _normalize_subscription(rows[0])


def ensure_user_subscription(*, user_id: int | None) -> dict[str, Any] | None:
    if user_id is None:
        return None
    existing = get_active_subscription(user_id=user_id)
    if existing:
        return existing
    payload = {
        "user_id": user_id,
        "plan": "free",
        "status": "active",
        "provider": "system",
        "requests_limit": FREE_LIMIT,
        "requests_used": 0,
        "current_period_start": _now_iso(),
        "current_period_end": _free_period_end(),
        "updated_at": _now_iso(),
    }
    response = get_supabase_client().table("subscriptions").insert(payload).execute()
    rows = _rows(response)
    return _normalize_subscription(rows[0] if rows else payload)


def can_run_parser(*, user_id: int | None) -> tuple[bool, dict[str, Any] | None]:
    subscription = ensure_user_subscription(user_id=user_id)
    if not subscription:
        return False, None
    return bool(subscription["remaining"] > 0), subscription


def consume_parser_credit(*, user_id: int | None) -> dict[str, Any] | None:
    subscription = ensure_user_subscription(user_id=user_id)
    if not subscription or subscription["id"] is None:
        return subscription
    next_used = min(subscription["requests_used"] + 1, subscription["requests_limit"])
    response = (
        get_supabase_client()
        .table("subscriptions")
        .update({"requests_used": next_used, "updated_at": _now_iso()})
        .eq("id", subscription["id"])
        .execute()
    )
    rows = _rows(response)
    return _normalize_subscription(rows[0] if rows else {**subscription, "requests_used": next_used})


def quota_payload(subscription: dict[str, Any] | None) -> dict[str, Any]:
    subscription = subscription or {}
    limit = int(subscription.get("requests_limit") or FREE_LIMIT)
    used = int(subscription.get("requests_used") or 0)
    remaining = max(limit - used, 0)
    plan = str(subscription.get("plan") or ("paid" if limit > FREE_LIMIT else "free"))
    return {
        "remaining": remaining,
        "used": used,
        "limit": limit,
        "plan_type": plan,
        "unlimited": False,
    }
