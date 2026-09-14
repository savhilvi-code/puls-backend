from __future__ import annotations

from app.database.supabase import get_supabase_client
from app.services.link_service import extract_videos, normalize_media_type
from app.services.puls_data_service import _canonical_url


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
        url = _canonical_url(str(item.get("url") or "").strip())
        exists = (
            client.table("media_files")
            .select("id")
            .eq("user_id", user_id)
            .eq("file_url", url)
            .limit(1)
            .execute()
        )
        if getattr(exists, "data", []) or []:
            continue
        storage_type = normalize_media_type(item.get("type") or ("video" if item in extract_videos(all_links) else "document"))
        if not storage_type:
            continue
        client.table("media_files").insert(
            {
                "user_id": user_id,
                "vehicle_id": vehicle_id,
                "request_id": diagnostic_request_id,
                "media_type": storage_type,
                "file_url": url,
                "thumbnail_url": str(item.get("thumbnail_url") or "").strip() or None,
                "duration": item.get("duration"),
                "description": str(item.get("description") or item.get("title") or "").strip(),
            }
        ).execute()
