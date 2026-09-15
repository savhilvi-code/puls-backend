from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Request

from app.database.supabase import get_supabase_client, rows
from app.services.auth_service import resolve_identity
from app.services.subscription_service import FREE_LIMIT, PAID_LIMIT


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_admin(request: Request) -> str:
    """
    Verify Supabase Bearer token and require membership in admin_accounts.
    Returns authenticated administrator user_id.
    """
    identity = resolve_identity(request)

    if not identity.user_id or not identity.is_verified:
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
        )

    try:
        response = (
            get_supabase_client()
            .table("admin_accounts")
            .select("user_id")
            .eq("user_id", identity.user_id)
            .limit(1)
            .execute()
        )
        found = rows(response)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Failed to verify administrator permissions.",
        ) from exc

    if not found:
        raise HTTPException(
            status_code=403,
            detail="Administrator access required.",
        )

    return identity.user_id


def list_users() -> list[dict[str, Any]]:
    """
    Return users prepared by the admin_users database view.
    """
    try:
        response = (
            get_supabase_client()
            .table("admin_users")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        return rows(response)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Failed to load users.",
        ) from exc


def get_admin_user(user_id: str) -> dict[str, Any]:
    try:
        response = (
            get_supabase_client()
            .table("admin_users")
            .select("*")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        found = rows(response)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Failed to load user.",
        ) from exc

    if not found:
        raise HTTPException(
            status_code=404,
            detail="User not found.",
        )

    return found[0]


def reset_user_quota(user_id: str) -> dict[str, Any]:
    user = get_admin_user(user_id)

    plan = str(user.get("plan") or "free").lower()
    quota_limit = PAID_LIMIT if plan == "paid" else FREE_LIMIT

    try:
        response = (
            get_supabase_client()
            .table("subscriptions")
            .update(
                {
                    "quota_limit": quota_limit,
                    "quota_used": 0,
                    "updated_at": _now_iso(),
                }
            )
            .eq("user_id", user_id)
            .in_("status", ["active", "trialing"])
            .execute()
        )
        updated = rows(response)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Failed to reset user quota.",
        ) from exc

    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Active subscription not found.",
        )

    return {
        "user_id": user_id,
        "plan": plan,
        "quota_limit": quota_limit,
        "quota_used": 0,
        "remaining": quota_limit,
    }


def change_user_plan(user_id: str, plan: str) -> dict[str, Any]:
    get_admin_user(user_id)

    normalized_plan = str(plan or "").strip().lower()

    if normalized_plan not in {"free", "paid"}:
        raise HTTPException(
            status_code=400,
            detail="Plan must be 'free' or 'paid'.",
        )

    quota_limit = PAID_LIMIT if normalized_plan == "paid" else FREE_LIMIT

    try:
        response = (
            get_supabase_client()
            .table("subscriptions")
            .update(
                {
                    "plan": normalized_plan,
                    "status": "active",
                    "quota_limit": quota_limit,
                    "quota_used": 0,
                    "updated_at": _now_iso(),
                }
            )
            .eq("user_id", user_id)
            .in_("status", ["active", "trialing", "inactive"])
            .execute()
        )
        updated = rows(response)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Failed to change user plan.",
        ) from exc

    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Subscription not found.",
        )

    return {
        "user_id": user_id,
        "plan": normalized_plan,
        "status": "active",
        "quota_limit": quota_limit,
        "quota_used": 0,
        "remaining": quota_limit,
    }


def _auth_admin():
    client = get_supabase_client()
    admin = getattr(client.auth, "admin", None)

    if admin is None:
        raise HTTPException(
            status_code=503,
            detail="Supabase Auth Admin API is unavailable.",
        )

    return admin


def block_user(user_id: str) -> dict[str, Any]:
    get_admin_user(user_id)

    try:
        _auth_admin().update_user_by_id(
            user_id,
            {
                "ban_duration": "876000h",
            },
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Failed to block user.",
        ) from exc

    return {
        "user_id": user_id,
        "blocked": True,
    }


def unblock_user(user_id: str) -> dict[str, Any]:
    get_admin_user(user_id)

    try:
        _auth_admin().update_user_by_id(
            user_id,
            {
                "ban_duration": "none",
            },
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Failed to unblock user.",
        ) from exc

    return {
        "user_id": user_id,
        "blocked": False,
    }


def delete_user_permanently(
    user_id: str,
    *,
    acting_admin_id: str,
) -> dict[str, Any]:
    """
    Delete PULS personal data transactionally through PostgreSQL,
    then remove the corresponding Supabase Auth account.
    """

    user = get_admin_user(user_id)

    if user_id == acting_admin_id:
        raise HTTPException(
            status_code=400,
            detail="Administrator cannot delete their own account.",
        )

    try:
        admin_check = (
            get_supabase_client()
            .table("admin_accounts")
            .select("user_id")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )

        if rows(admin_check):
            raise HTTPException(
                status_code=409,
                detail="Administrator accounts cannot be deleted here.",
            )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Failed to verify target account.",
        ) from exc

    try:
        get_supabase_client().rpc(
            "admin_delete_user_data",
            {
                "target_user_id": user_id,
            },
        ).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Failed to delete PULS user data.",
        ) from exc

    try:
        _auth_admin().delete_user(user_id)
    except Exception as exc:
        # At this point the PULS data transaction has already succeeded.
        # Report the Auth failure explicitly instead of pretending that
        # the complete account deletion succeeded.
        raise HTTPException(
            status_code=503,
            detail=(
                "PULS user data was deleted, but the Supabase Auth "
                "account could not be deleted."
            ),
        ) from exc

    return {
        "deleted": True,
        "user_id": user_id,
        "email": user.get("email"),
    }
