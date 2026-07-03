import os
from functools import lru_cache
from typing import Any

from supabase import Client, create_client


class SupabaseUnavailableError(RuntimeError):
    pass


class SupabaseOperationError(RuntimeError):
    pass


def _env_value(name: str) -> str:
    return str(os.getenv(name, "") or "").strip()


def is_supabase_configured() -> bool:
    return bool(_env_value("SUPABASE_URL") and _env_value("SUPABASE_KEY"))


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    url = _env_value("SUPABASE_URL")
    key = _env_value("SUPABASE_KEY")
    if not url or not key:
        raise SupabaseUnavailableError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY.")
    if url.endswith("/rest/v1") or url.endswith("/rest/v1/"):
        url = url[: url.index("/rest/v1")]
    try:
        return create_client(url, key)
    except Exception as exc:  # pragma: no cover - transport/config failures
        raise SupabaseUnavailableError(f"Failed to initialize Supabase client: {exc}") from exc


def _client() -> Client:
    return get_supabase_client()


def _map_user_row(row: dict[str, Any]):
    from app.schemas.user import UserRecord

    return UserRecord(
        id=row.get("id"),
        auth_user_id=row.get("auth_user_id") or "",
        email=row.get("email") or "",
        username=row.get("name") or "",
        first_name="",
        car_info=row.get("car_info") or "",
        language=row.get("language") or "en",
        conversation_history=row.get("conversation_history") or "",
        requests_left=int(row.get("requests_left") or 0),
    )


def find_user_by_fields(*, auth_user_id: str = "", email: str = ""):
    if not is_supabase_configured():
        raise SupabaseUnavailableError("Supabase is not configured.")

    filters = []
    if auth_user_id:
        filters.append(("auth_user_id", auth_user_id))
    if email:
        filters.append(("email", email))

    if not filters:
        return None

    last_error: Exception | None = None
    for column, value in filters:
        try:
            response = _client().table("users").select("*").eq(column, value).limit(1).execute()
            rows = getattr(response, "data", []) or []
            if rows:
                return _map_user_row(rows[0])
        except Exception as exc:
            last_error = exc

    if last_error is not None:
        raise SupabaseOperationError(f"Failed to find user: {last_error}") from last_error
    return None


def create_user_record(payload: dict[str, Any]):
    if not is_supabase_configured():
        raise SupabaseUnavailableError("Supabase is not configured.")

    try:
        response = _client().table("users").insert(payload).execute()
        rows = getattr(response, "data", []) or []
        if not rows:
            raise SupabaseOperationError("Supabase insert returned no rows.")
        return _map_user_row(rows[0])
    except Exception as exc:
        raise SupabaseOperationError(f"Failed to create user: {exc}") from exc


def update_user_record(user_id: int, payload: dict[str, Any]):
    if not is_supabase_configured():
        raise SupabaseUnavailableError("Supabase is not configured.")

    try:
        response = _client().table("users").update(payload).eq("id", user_id).execute()
        rows = getattr(response, "data", []) or []
        if rows:
            return _map_user_row(rows[0])
        return None
    except Exception as exc:
        raise SupabaseOperationError(f"Failed to update user: {exc}") from exc


def decrement_requests_left(user_id: int):
    if not is_supabase_configured():
        raise SupabaseUnavailableError("Supabase is not configured.")

    user = get_user_by_id(user_id)
    if user is None:
        raise SupabaseOperationError("User not found while decrementing requests_left.")

    next_value = max(int(user.requests_left or 0) - 1, 0)
    return update_user_record(user_id, {"requests_left": next_value})


def update_conversation_history(user_id: int, conversation_history: str):
    return update_user_record(user_id, {"conversation_history": conversation_history})


def update_car_info(user_id: int, car_info: str):
    return update_user_record(user_id, {"car_info": car_info})


def get_user_by_id(user_id: int):
    if not is_supabase_configured():
        raise SupabaseUnavailableError("Supabase is not configured.")

    try:
        response = _client().table("users").select("*").eq("id", user_id).limit(1).execute()
        rows = getattr(response, "data", []) or []
        if rows:
            return _map_user_row(rows[0])
        return None
    except Exception as exc:
        raise SupabaseOperationError(f"Failed to get user by id: {exc}") from exc


def find_knowledge_case(*, text: str, car_info: str):
    if not is_supabase_configured():
        raise SupabaseUnavailableError("Supabase is not configured.")

    try:
        query = _client().table("knowledge_cases").select("*").ilike("symptom_title", f"%{text.strip()}%").limit(5)
        response = query.execute()
        return getattr(response, "data", []) or []
    except Exception as exc:
        raise SupabaseOperationError(f"Failed to search knowledge cases: {exc}") from exc


def create_knowledge_case(payload: dict[str, Any]):
    if not is_supabase_configured():
        raise SupabaseUnavailableError("Supabase is not configured.")

    try:
        response = _client().table("knowledge_cases").insert(payload).execute()
        rows = getattr(response, "data", []) or []
        return rows[0] if rows else None
    except Exception as exc:
        raise SupabaseOperationError(f"Failed to create knowledge case: {exc}") from exc
