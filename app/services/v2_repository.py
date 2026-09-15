from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse, urlunparse

from app.database.supabase import get_supabase_client, rows


V2_PUBLIC_TABLES = (
    "users",
    "subscriptions",
    "payments",
    "vehicles",
    "vehicle_specs",
    "conversations",
    "messages",
    "problems",
    "vehicle_events",
    "vehicle_configurations",
    "fleet_events",
    "knowledge_items",
    "sources",
    "knowledge_sources",
    "problem_sources",
    "search_episodes",
    "search_runs",
)


ACTIVE_VEHICLE_STATUSES = ("ACTIVE", "active", "", None)
OPEN_PROBLEM_STATUSES = ("OPEN", "ACTIVE", "INVESTIGATING", "AWAITING_CONFIRMATION", "open", "active", "investigating")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def canonical_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    if "youtu.be" in netloc:
        video_id = path.strip("/").split("/", 1)[0]
        return f"https://www.youtube.com/watch?v={video_id}" if video_id else raw
    if "youtube.com" in netloc:
        video_id = parse_qs(parsed.query).get("v", [""])[0]
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"
    return urlunparse((scheme, netloc, path, "", "", ""))


def _one(response) -> dict[str, Any] | None:
    found = rows(response)
    return found[0] if found else None


def list_user_vehicles(*, user_id: int | None, include_trashed: bool = False) -> list[dict[str, Any]]:
    if user_id is None:
        return []
    query = get_supabase_client().table("vehicles").select("*").eq("user_id", user_id)
    if not include_trashed:
        query = query.neq("lifecycle_status", "TRASHED")
    return rows(query.order("updated_at", desc=True).limit(100).execute())


def get_vehicle(*, user_id: int | None, vehicle_id: int | None, include_trashed: bool = False) -> dict[str, Any] | None:
    if user_id is None or vehicle_id is None:
        return None
    query = get_supabase_client().table("vehicles").select("*").eq("user_id", user_id).eq("id", vehicle_id).limit(1)
    if not include_trashed:
        query = query.neq("lifecycle_status", "TRASHED")
    return _one(query.execute())


def save_vehicle(*, user_id: int | None, payload: dict[str, Any], vehicle_id: int | None = None) -> dict[str, Any] | None:
    if user_id is None:
        return None
    data = _clean_payload({**payload, "user_id": user_id, "updated_at": now_iso()})
    client = get_supabase_client()
    if vehicle_id:
        response = client.table("vehicles").update(data).eq("id", vehicle_id).eq("user_id", user_id).execute()
    else:
        data.setdefault("lifecycle_status", "ACTIVE")
        response = client.table("vehicles").insert(data).execute()
    return _one(response)


def soft_delete_vehicle(*, user_id: int | None, vehicle_id: int | None, retention_days: int = 30) -> bool:
    if user_id is None or vehicle_id is None:
        return False
    now = datetime.now(timezone.utc)
    payload = {
        "lifecycle_status": "TRASHED",
        "trashed_at": now.isoformat(),
        "restore_until": (now + timedelta(days=retention_days)).isoformat(),
        "updated_at": now.isoformat(),
    }
    response = get_supabase_client().table("vehicles").update(payload).eq("id", vehicle_id).eq("user_id", user_id).execute()
    return bool(rows(response))


def restore_vehicle(*, user_id: int | None, vehicle_id: int | None) -> dict[str, Any] | None:
    if user_id is None or vehicle_id is None:
        return None
    payload = {"lifecycle_status": "ACTIVE", "trashed_at": None, "restore_until": None, "updated_at": now_iso()}
    response = (
        get_supabase_client()
        .table("vehicles")
        .update(payload)
        .eq("id", vehicle_id)
        .eq("user_id", user_id)
        .eq("lifecycle_status", "TRASHED")
        .execute()
    )
    return _one(response)


def get_vehicle_specs(*, user_id: int | None, vehicle_id: int | None) -> dict[str, Any] | None:
    vehicle = get_vehicle(user_id=user_id, vehicle_id=vehicle_id)
    if not vehicle:
        return None
    response = get_supabase_client().table("vehicle_specs").select("*").eq("vehicle_id", vehicle_id).limit(1).execute()
    return _one(response)


def upsert_vehicle_specs(*, user_id: int | None, vehicle_id: int | None, payload: dict[str, Any]) -> dict[str, Any] | None:
    if not get_vehicle(user_id=user_id, vehicle_id=vehicle_id):
        return None
    client = get_supabase_client()
    existing = _one(client.table("vehicle_specs").select("id").eq("vehicle_id", vehicle_id).limit(1).execute())
    data = _clean_payload({**payload, "vehicle_id": vehicle_id, "updated_at": now_iso()})
    if existing:
        response = client.table("vehicle_specs").update(data).eq("id", existing["id"]).execute()
    else:
        response = client.table("vehicle_specs").insert(data).execute()
    return _one(response)


def get_or_create_conversation(
    *,
    user_id: int | None,
    vehicle_id: int | None = None,
    problem_id: int | None = None,
    title: str = "",
    conversation_id: int | None = None,
) -> dict[str, Any] | None:
    if user_id is None:
        return None
    client = get_supabase_client()
    if conversation_id:
        existing = _one(
            client.table("conversations")
            .select("*")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if existing:
            return existing

    payload = {
        "user_id": user_id,
        "vehicle_id": vehicle_id,
        "problem_id": problem_id,
        "channel": "site",
        "status": "active",
        "title": title[:160],
        "last_message_at": now_iso(),
        "updated_at": now_iso(),
    }
    response = client.table("conversations").insert(_clean_payload(payload)).execute()
    return _one(response)


def save_message(
    *,
    user_id: int | None,
    conversation_id: int | None,
    role: str,
    text: str,
    vehicle_id: int | None = None,
    problem_id: int | None = None,
    language: str = "en",
) -> dict[str, Any] | None:
    if user_id is None or conversation_id is None or not str(text or "").strip():
        return None
    payload = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "vehicle_id": vehicle_id,
        "problem_id": problem_id,
        "role": role,
        "message_text": str(text or "").strip(),
        "language": language or "en",
    }
    return _one(get_supabase_client().table("messages").insert(_clean_payload(payload)).execute())


def recent_conversation_messages(*, user_id: int | None, conversation_id: int | None = None, limit: int = 12) -> list[dict[str, Any]]:
    if user_id is None:
        return []
    client = get_supabase_client()
    if conversation_id is None:
        latest = _one(
            client.table("conversations")
            .select("id")
            .eq("user_id", user_id)
            .eq("status", "active")
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        conversation_id = latest.get("id") if latest else None
    if conversation_id is None:
        return []
    found = rows(
        client.table("messages")
        .select("*")
        .eq("conversation_id", conversation_id)
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return list(reversed(found))


def list_problems(
    *,
    user_id: int | None,
    vehicle_id: int | None = None,
    statuses: tuple[str, ...] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if user_id is None:
        return []
    query = get_supabase_client().table("problems").select("*").eq("user_id", user_id)
    if vehicle_id is not None:
        query = query.eq("vehicle_id", vehicle_id)
    if statuses:
        query = query.in_("status", list(statuses))
    return rows(query.order("updated_at", desc=True).limit(limit).execute())


def get_problem(*, user_id: int | None, problem_id: int | None) -> dict[str, Any] | None:
    if user_id is None or problem_id is None:
        return None
    return _one(
        get_supabase_client()
        .table("problems")
        .select("*")
        .eq("id", problem_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )


def save_problem(*, user_id: int | None, vehicle_id: int | None, payload: dict[str, Any], problem_id: int | None = None) -> dict[str, Any] | None:
    if user_id is None or vehicle_id is None:
        return None
    base = {
        **payload,
        "user_id": user_id,
        "vehicle_id": vehicle_id,
        "last_seen_at": now_iso(),
        "updated_at": now_iso(),
    }
    client = get_supabase_client()
    if problem_id:
        response = client.table("problems").update(_clean_payload(base)).eq("id", problem_id).eq("user_id", user_id).execute()
    else:
        base.setdefault("status", "OPEN")
        base.setdefault("first_seen_at", now_iso())
        response = client.table("problems").insert(_clean_payload(base)).execute()
    return _one(response)


def list_vehicle_events(*, user_id: int | None, vehicle_id: int | None, problem_id: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
    if user_id is None or vehicle_id is None:
        return []
    query = get_supabase_client().table("vehicle_events").select("*").eq("user_id", user_id).eq("vehicle_id", vehicle_id)
    if problem_id is not None:
        query = query.eq("problem_id", problem_id)
    return rows(query.order("occurred_at", desc=True).limit(limit).execute())


def create_vehicle_event(*, user_id: int | None, vehicle_id: int | None, problem_id: int | None, payload: dict[str, Any]) -> dict[str, Any] | None:
    if user_id is None or vehicle_id is None:
        return None
    data = {
        **payload,
        "user_id": user_id,
        "vehicle_id": vehicle_id,
        "problem_id": problem_id,
        "occurred_at": payload.get("occurred_at") or now_iso(),
    }
    return _one(get_supabase_client().table("vehicle_events").insert(_clean_payload(data)).execute())


def create_search_episode(*, user_id: int | None, vehicle_id: int | None, problem_id: int | None, reason: str) -> dict[str, Any] | None:
    if user_id is None or problem_id is None:
        return None
    payload = {
        "user_id": user_id,
        "vehicle_id": vehicle_id,
        "problem_id": problem_id,
        "status": "RUNNING",
        "reason": reason,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    return _one(get_supabase_client().table("search_episodes").insert(_clean_payload(payload)).execute())


def update_search_episode(*, user_id: int | None, episode_id: int | None, payload: dict[str, Any]) -> dict[str, Any] | None:
    if user_id is None or episode_id is None:
        return None
    data = {**payload, "updated_at": now_iso()}
    return _one(
        get_supabase_client()
        .table("search_episodes")
        .update(_clean_payload(data))
        .eq("id", episode_id)
        .eq("user_id", user_id)
        .execute()
    )


def create_search_run(*, user_id: int | None, episode_id: int | None, payload: dict[str, Any]) -> dict[str, Any] | None:
    if user_id is None or episode_id is None:
        return None
    data = {**payload, "user_id": user_id, "search_episode_id": episode_id, "created_at": now_iso()}
    return _one(get_supabase_client().table("search_runs").insert(_clean_payload(data)).execute())


def upsert_source(source: dict[str, Any]) -> dict[str, Any] | None:
    url = canonical_url(str(source.get("url") or source.get("canonical_url") or ""))
    if not url:
        return None
    client = get_supabase_client()
    existing = _one(client.table("sources").select("*").eq("canonical_url", url).limit(1).execute())
    payload = {
        "canonical_url": url,
        "title": str(source.get("title") or url).strip(),
        "description": str(source.get("description") or "").strip(),
        "source_type": str(source.get("type") or source.get("source_type") or "external").strip(),
        "metadata": source.get("metadata") or {},
        "updated_at": now_iso(),
    }
    if existing:
        return _one(client.table("sources").update(_clean_payload(payload)).eq("id", existing["id"]).execute())
    return _one(client.table("sources").insert(_clean_payload(payload)).execute())


def link_problem_source(
    *,
    user_id: int | None,
    problem_id: int | None,
    source_id: int | None,
    search_run_id: int | None,
    summary: str,
    relevance: float = 0.5,
) -> dict[str, Any] | None:
    if user_id is None or problem_id is None or source_id is None:
        return None
    payload = {
        "user_id": user_id,
        "problem_id": problem_id,
        "source_id": source_id,
        "search_run_id": search_run_id,
        "evidence_summary": summary,
        "relevance": relevance,
    }
    return _one(get_supabase_client().table("problem_sources").insert(_clean_payload(payload)).execute())


def find_relevant_knowledge(*, vehicle: dict[str, Any] | None, symptom: str, limit: int = 5) -> list[dict[str, Any]]:
    text = " ".join(str(symptom or "").split())
    if not text:
        return []
    query = get_supabase_client().table("knowledge_items").select("*").limit(limit)
    vehicle = vehicle or {}
    if vehicle.get("brand"):
        query = query.ilike("vehicle_make", f"%{vehicle['brand']}%")
    token = next((part for part in text.split() if len(part) >= 5), "")
    if token:
        query = query.ilike("summary", f"%{token}%")
    return rows(query.execute())


def list_problem_sources(*, user_id: int | None, problem_id: int | None, limit: int = 20) -> list[dict[str, Any]]:
    if user_id is None or problem_id is None:
        return []
    return rows(
        get_supabase_client()
        .table("problem_sources")
        .select("*, sources(*)")
        .eq("user_id", user_id)
        .eq("problem_id", problem_id)
        .limit(limit)
        .execute()
    )
