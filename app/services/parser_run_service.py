from __future__ import annotations

from app.database.supabase import get_supabase_client
from app.services.puls_data_service import extract_videos


def _rows(response) -> list[dict]:
    return getattr(response, "data", []) or []


def create_parser_run(
    *,
    user_id: int | None,
    vehicle_id: int | None,
    conversation_id: int | None,
    diagnostic_request_id: int | None,
    run_type: str,
    query_original: str,
    parsed_case: dict,
) -> dict | None:
    if user_id is None:
        return None
    raw = parsed_case.get("_raw") if isinstance(parsed_case, dict) else {}
    meta = raw.get("_meta") if isinstance(raw, dict) else {}
    links = parsed_case.get("links") if isinstance(parsed_case, dict) else []
    forums_used = parsed_case.get("forums_found") if isinstance(parsed_case, dict) else None
    payload = {
        "user_id": user_id,
        "vehicle_id": vehicle_id,
        "conversation_id": conversation_id,
        "diagnostic_request_id": diagnostic_request_id,
        "run_type": run_type,
        "query_original": query_original,
        "query_translated": raw.get("query_translated") if isinstance(raw, dict) else None,
        "languages_used": raw.get("languages_used") if isinstance(raw, dict) else None,
        "forums_used": forums_used,
        "sources_found": links or [],
        "videos_found": extract_videos(links or []),
        "tokens_used": meta.get("tokens_used") if isinstance(meta, dict) else None,
    }
    response = get_supabase_client().table("parser_runs").insert(payload).execute()
    rows = _rows(response)
    return rows[0] if rows else None
