from __future__ import annotations

from fastapi import HTTPException

from app.database.supabase import SupabaseOperationError, SupabaseUnavailableError, get_supabase_client
from datetime import datetime, timezone


def _format_created_at(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone().strftime("%d.%m.%Y, %H:%M")
    except Exception:
        return raw


def _derive_status(message_type: str) -> str:
    message_type = str(message_type or "").strip().lower()
    if message_type in {"greeting", "limit"}:
        return message_type
    if message_type in {"feedback_helped", "resolved"}:
        return "resolved"
    if message_type in {"feedback_not_helped", "followup_deep"}:
        return "followup"
    if message_type in {"clarification", "new_diagnostic", "parser", "kb_match", "followup"}:
        return "open"
    return "open"


async def save_diagnostic_request(*, user_id: int | None, normalized, answer: str, message_type: str, vehicle_id: int | None = None, vehicle_profile_id: int | None = None) -> dict | None:
    if user_id is None:
        return None

    status = _derive_status(message_type)
    if status == "greeting":
        return None

    payload = {
        "user_id": user_id,
        "vehicle_id": vehicle_id,
        "vehicle_profile_id": vehicle_profile_id,
        "question": str(normalized.text or "").strip(),
        "answer": str(answer or "").strip(),
        "language": str(normalized.language or "ru"),
        "request_type": "text",
        "status": status,
        "source": str(normalized.source or "web"),
    }

    try:
        client = get_supabase_client()
        response = client.table("diagnostic_requests").insert(payload).execute()
        rows = getattr(response, "data", []) or []
        return rows[0] if rows else None
    except SupabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SupabaseOperationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Failed to save diagnostic request: {exc}") from exc


async def get_user_request_history(*, user_id: int | None = None, email: str = "", limit: int = 50) -> list[dict]:
    if limit <= 0:
        limit = 50

    try:
        client = get_supabase_client()
    except SupabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    resolved_user_id = user_id
    if resolved_user_id is None and email:
        try:
            user_response = client.table("users").select("id,car_info,email").eq("email", email).limit(1).execute()
            user_rows = getattr(user_response, "data", []) or []
            if user_rows:
                resolved_user_id = user_rows[0].get("id")
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Failed to resolve user history owner: {exc}") from exc

    if resolved_user_id is None:
        return []

    try:
        response = (
            client.table("diagnostic_requests")
            .select("id,user_id,vehicle_id,vehicle_profile_id,question,answer,language,request_type,status,source,created_at")
            .eq("user_id", resolved_user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = getattr(response, "data", []) or []
    except SupabaseOperationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Failed to load diagnostic history: {exc}") from exc

    items: list[dict] = []
    for row in rows:
        items.append(
            {
                "id": row.get("id"),
                "question": row.get("question") or "",
                "answer": row.get("answer") or "",
                "date": _format_created_at(row.get("created_at")),
                "status": row.get("status") or "",
                "vehicle": row.get("vehicle_id") or row.get("vehicle_profile_id") or "",
                "type": row.get("request_type") or "text",
                "source": row.get("source") or "web",
                "created_at": row.get("created_at") or "",
            }
        )

    return items
