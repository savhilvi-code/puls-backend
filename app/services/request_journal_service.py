from __future__ import annotations

from fastapi import HTTPException

from app.database.supabase import SupabaseOperationError, SupabaseUnavailableError, get_supabase_client


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
