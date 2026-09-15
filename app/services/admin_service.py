from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Request

from app.database.supabase import get_supabase_client, rows
from app.services.auth_service import resolve_identity
from app.services.subscription_service import FREE_LIMIT, PAID_LIMIT


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _auth_admin():
    client = get_supabase_client()
    admin = getattr(client.auth, "admin", None)

    if admin is None:
        raise HTTPException(
            status_code=503,
            detail="Supabase Auth Admin API is unavailable.",
        )

    return admin


def _extract_auth_user(response: Any) -> Any | None:
    """
    supabase-py Auth Admin responses can expose the user either directly
    through .user or through a response data object depending on version.
    """
    if response is None:
        return None

    user = getattr(response, "user", None)
    if user is not None:
        return user

    data = getattr(response, "data", None)
    if data is not None:
        user = getattr(data, "user", None)
        if user is not None:
            return user

        if isinstance(data, dict):
            return data.get("user")

    if isinstance(response, dict):
        return response.get("user") or response.get("data", {}).get("user")

    return None


def _auth_user_block_state(user_id: str) -> dict[str, Any]:
    """
    Read the real block state from Supabase Auth.
    A user is blocked while banned_until is in the future.
    """
    try:
        response = _auth_admin().get_user_by_id(user_id)
        auth_user = _extract_auth_user(response)
    except Exception:
        return {
            "blocked": False,
            "banned_until": None,
            "auth_status_available": False,
        }

    if auth_user is None:
        return {
            "blocked": False,
            "banned_until": None,
            "auth_status_available": False,
        }

    if isinstance(auth_user, dict):
        banned_until = auth_user.get("banned_until")
    else:
        banned_until = getattr(auth_user, "banned_until", None)

    blocked = False

    if banned_until:
        try:
            value = str(banned_until).replace("Z", "+00:00")
            banned_until_dt = datetime.fromisoformat(value)

            if banned_until_dt.tzinfo is None:
                banned_until_dt = banned_until_dt.replace(tzinfo=timezone.utc)

            blocked = banned_until_dt > datetime.now(timezone.utc)
        except (TypeError, ValueError):
            # If Supabase reports a non-empty ban value that cannot be parsed,
            # treat it as blocked rather than incorrectly showing the account
            # as active.
            blocked = True

    return {
        "blocked": blocked,
        "banned_until": str(banned_until) if banned_until else None,
        "auth_status_available": True,
    }


def _with_auth_state(user: dict[str, Any]) -> dict[str, Any]:
    result = dict(user)
    user_id = result.get("user_id")

    if not user_id:
        result.update(
            {
                "blocked": False,
                "banned_until": None,
                "auth_status_available": False,
            }
        )
        return result

    result.update(_auth_user_block_state(str(user_id)))
    return result


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
    Return users prepared by the admin_users database view,
    enriched with their real Supabase Auth block state.
    """
    try:
        response = (
            get_supabase_client()
            .table("admin_users")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        users = rows(response)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Failed to load users.",
        ) from exc

    return [_with_auth_state(user) for user in users]


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

    return _with_auth_state(found[0])


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
