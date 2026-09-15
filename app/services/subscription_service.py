from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.database.supabase import get_supabase_client, rows

FREE_LIMIT = 10
PAID_LIMIT = 100


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _free_period_end() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=3650)).isoformat()


def _int_value(row: dict[str, Any], key: str, default: int) -> int:
    raw = row.get(key)
    try:
        return int(raw if raw is not None else default)
    except (TypeError, ValueError):
        return default


def _normalize_subscription(row: dict[str, Any] | None) -> dict[str, Any]:
    row = row or {}
    plan = str(row.get("plan") or "free")
    limit = _int_value(row, "quota_limit", PAID_LIMIT if plan == "paid" else FREE_LIMIT)
    used = _int_value(row, "quota_used", 0)
    used = min(max(used, 0), max(limit, 0))
    return {
        "id": row.get("id"),
        "user_id": row.get("user_id"),
        "plan": plan,
        "status": str(row.get("status") or "active"),
        "provider": row.get("provider"),
        "provider_customer_id": row.get("provider_customer_id"),
        "provider_subscription_id": row.get("provider_subscription_id"),
        "quota_limit": limit,
        "quota_used": used,
        "remaining": max(limit - used, 0),
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
    found = rows(response)
    if not found:
        return None
    for row in found:
        if str(row.get("status") or "").lower() in {"active", "trialing"}:
            return _normalize_subscription(row)
    return _normalize_subscription(found[0])


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
        "quota_limit": FREE_LIMIT,
        "quota_used": 0,
        "current_period_start": _now_iso(),
        "current_period_end": _free_period_end(),
        "updated_at": _now_iso(),
    }
    response = get_supabase_client().table("subscriptions").insert(payload).execute()
    found = rows(response)
    return _normalize_subscription(found[0] if found else payload)


def can_run_research(*, user_id: int | None) -> tuple[bool, dict[str, Any] | None]:
    subscription = ensure_user_subscription(user_id=user_id)
    if not subscription:
        return False, None
    return bool(subscription["remaining"] > 0), subscription


def consume_research_credit(*, user_id: int | None) -> dict[str, Any] | None:
    subscription = ensure_user_subscription(user_id=user_id)
    if not subscription or subscription["id"] is None:
        return subscription
    next_used = min(int(subscription["quota_used"]) + 1, int(subscription["quota_limit"]))
    response = (
        get_supabase_client()
        .table("subscriptions")
        .update({"quota_used": next_used, "updated_at": _now_iso()})
        .eq("id", subscription["id"])
        .eq("user_id", user_id)
        .execute()
    )
    found = rows(response)
    return _normalize_subscription(found[0] if found else {**subscription, "quota_used": next_used})


def quota_payload(subscription: dict[str, Any] | None) -> dict[str, Any]:
    subscription = _normalize_subscription(subscription)
    return {
        "remaining": subscription["remaining"],
        "used": subscription["quota_used"],
        "limit": subscription["quota_limit"],
        "plan_type": subscription["plan"],
        "unlimited": False,
    }
