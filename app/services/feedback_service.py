from __future__ import annotations

from app.database.supabase import get_supabase_client


def _rows(response) -> list[dict]:
    return getattr(response, "data", []) or []


def create_feedback(
    *,
    user_id: int | None,
    vehicle_id: int | None,
    conversation_id: int | None,
    diagnostic_request_id: int | None,
    feedback_type: str,
    feedback_text: str,
) -> dict | None:
    if user_id is None or not feedback_type:
        return None
    response = get_supabase_client().table("user_feedback").insert(
        {
            "user_id": user_id,
            "vehicle_id": vehicle_id,
            "conversation_id": conversation_id,
            "diagnostic_request_id": diagnostic_request_id,
            "feedback_type": feedback_type,
            "feedback_text": feedback_text,
        }
    ).execute()
    rows = _rows(response)
    return rows[0] if rows else None
