from __future__ import annotations

from app.database.supabase import get_supabase_client
from app.services.link_service import extract_videos


def save_media_files(
    *,
    user_id: int | None,
    vehicle_id: int | None,
    diagnostic_request_id: int | None,
    links: list[dict] | None,
) -> None:
    if user_id is None:
        return
    client = get_supabase_client()
    all_links = links or []
    for item in all_links:
        if not isinstance(item, dict) or not str(item.get("url") or "").strip():
            continue
        client.table("media_files").insert(
            {
                "user_id": user_id,
                "vehicle_id": vehicle_id,
                "request_id": diagnostic_request_id,
                "media_type": "video" if item in extract_videos(all_links) else "document",
                "file_url": str(item.get("url") or "").strip(),
                "thumbnail_url": str(item.get("thumbnail_url") or "").strip() or None,
                "duration": item.get("duration"),
                "description": str(item.get("description") or item.get("title") or "").strip(),
            }
        ).execute()
