from __future__ import annotations

import base64
import json
import os
from functools import lru_cache
from typing import Any

from supabase import Client, create_client

from app.schemas.user import UserRecord


class SupabaseUnavailableError(RuntimeError):
    pass


class SupabaseOperationError(RuntimeError):
    pass


def _env_value(name: str) -> str:
    return str(os.getenv(name, "") or "").strip()


def _server_key() -> str:
    return (
        _env_value("SUPABASE_SERVICE_ROLE_KEY")
        or _env_value("SUPABASE_SECRET_KEY")
        or _env_value("SUPABASE_SERVICE_KEY")
    )


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8")
        data = json.loads(decoded)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def is_supabase_configured() -> bool:
    return bool(_env_value("SUPABASE_URL") and _server_key())


def supabase_key_source() -> str:
    if _env_value("SUPABASE_SERVICE_ROLE_KEY"):
        return "SUPABASE_SERVICE_ROLE_KEY"
    if _env_value("SUPABASE_SECRET_KEY"):
        return "SUPABASE_SECRET_KEY"
    if _env_value("SUPABASE_SERVICE_KEY"):
        return "SUPABASE_SERVICE_KEY"
    if _env_value("SUPABASE_KEY") or _env_value("SUPABASE_ANON_KEY"):
        return "publishable_key_ignored_for_server_writes"
    return ""


def supabase_env_names() -> list[str]:
    return sorted(name for name in os.environ if name.startswith("SUPABASE"))


def is_supabase_service_role_env_present() -> bool:
    return bool(_env_value("SUPABASE_SERVICE_ROLE_KEY"))


def is_supabase_service_key_configured() -> bool:
    key = _server_key()
    if not key:
        return False
    if key.startswith("sb_secret_"):
        return True
    payload = _decode_jwt_payload(key)
    return payload.get("role") == "service_role"


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    url = _env_value("SUPABASE_URL")
    key = _server_key()
    if not url or not key:
        raise SupabaseUnavailableError("Supabase server client is not configured.")
    if url.endswith("/rest/v1") or url.endswith("/rest/v1/"):
        url = url[: url.index("/rest/v1")]
    try:
        return create_client(url, key)
    except Exception as exc:  # pragma: no cover - transport/config failures
        raise SupabaseUnavailableError("Failed to initialize Supabase server client.") from exc


def rows(response) -> list[dict[str, Any]]:
    data = getattr(response, "data", []) or []
    return data if isinstance(data, list) else []


def _map_user_row(row: dict[str, Any]) -> UserRecord:
    return UserRecord(
        id=str(row.get("id") or "") or None,
        email=str(row.get("email") or ""),
        username=str(row.get("name") or row.get("full_name") or ""),
        first_name="",
        language=str(row.get("language") or "en"),
    )


def find_user_by_id(user_id: str) -> UserRecord | None:
    if not is_supabase_configured():
        raise SupabaseUnavailableError("Supabase is not configured.")

    user_id = str(user_id or "").strip()
    if not user_id:
        return None
    try:
        response = get_supabase_client().table("users").select("*").eq("id", user_id).limit(1).execute()
        found = rows(response)
        return _map_user_row(found[0]) if found else None
    except Exception as exc:
        raise SupabaseOperationError("Failed to find user profile.") from exc


def get_user_by_id(user_id: str) -> UserRecord | None:
    if not is_supabase_configured():
        raise SupabaseUnavailableError("Supabase is not configured.")
    try:
        response = get_supabase_client().table("users").select("*").eq("id", user_id).limit(1).execute()
        found = rows(response)
        return _map_user_row(found[0]) if found else None
    except Exception as exc:
        raise SupabaseOperationError("Failed to get user profile.") from exc


def create_user_record(payload: dict[str, Any]) -> UserRecord:
    if not is_supabase_configured():
        raise SupabaseUnavailableError("Supabase is not configured.")
    try:
        response = get_supabase_client().table("users").insert(payload).execute()
        found = rows(response)
        if not found:
            raise SupabaseOperationError("Supabase insert returned no profile row.")
        return _map_user_row(found[0])
    except SupabaseOperationError:
        raise
    except Exception as exc:
        raise SupabaseOperationError("Failed to create user profile.") from exc


def update_user_record(user_id: str, payload: dict[str, Any]) -> UserRecord | None:
    if not is_supabase_configured():
        raise SupabaseUnavailableError("Supabase is not configured.")
    try:
        response = get_supabase_client().table("users").update(payload).eq("id", user_id).execute()
        found = rows(response)
        return _map_user_row(found[0]) if found else None
    except Exception as exc:
        raise SupabaseOperationError("Failed to update user profile.") from exc


def get_auth_user_from_bearer(token: str) -> dict[str, str]:
    if not token:
        return {}
    try:
        auth_response = get_supabase_client().auth.get_user(token)
        auth_user = getattr(auth_response, "user", None)
        if auth_user is None:
            return {}
        return {
            "id": str(getattr(auth_user, "id", "") or ""),
            "email": str(getattr(auth_user, "email", "") or ""),
            "name": str((getattr(auth_user, "user_metadata", None) or {}).get("full_name") or ""),
        }
    except Exception as exc:
        raise SupabaseOperationError("Failed to verify Supabase auth token.") from exc
