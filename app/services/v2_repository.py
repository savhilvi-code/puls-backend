from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse, urlunparse

from app.database.supabase import (
    SupabaseOperationError,
    get_supabase_client,
    rows,
)


Uuid = str


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

OPEN_PROBLEM_STATUSES = (
    "OPEN",
    "ACTIVE",
    "INVESTIGATING",
    "AWAITING_CONFIRMATION",
    "open",
    "active",
    "investigating",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if value is not None
    }


def _one(response) -> dict[str, Any] | None:
    found = rows(response)
    return found[0] if found else None


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
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"

    if "youtube.com" in netloc:
        video_id = parse_qs(parsed.query).get("v", [""])[0]
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"

    return urlunparse(
        (
            scheme,
            netloc,
            path,
            "",
            parsed.query,
            "",
        )
    )


def _source_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------


def list_user_vehicles(
    *,
    user_id: Uuid | None,
    include_trashed: bool = False,
) -> list[dict[str, Any]]:
    if user_id is None:
        return []

    query = (
        get_supabase_client()
        .table("vehicles")
        .select("*")
        .eq("user_id", user_id)
    )

    if not include_trashed:
        query = query.neq("lifecycle_status", "TRASHED")

    return rows(
        query.order("updated_at", desc=True)
        .limit(100)
        .execute()
    )


def get_vehicle(
    *,
    user_id: Uuid | None,
    vehicle_id: Uuid | None,
    include_trashed: bool = False,
) -> dict[str, Any] | None:
    if user_id is None or vehicle_id is None:
        return None

    query = (
        get_supabase_client()
        .table("vehicles")
        .select("*")
        .eq("user_id", user_id)
        .eq("id", vehicle_id)
        .limit(1)
    )

    if not include_trashed:
        query = query.neq("lifecycle_status", "TRASHED")

    return _one(query.execute())


def save_vehicle(
    *,
    user_id: Uuid | None,
    payload: dict[str, Any],
    vehicle_id: Uuid | None = None,
) -> dict[str, Any] | None:
    if user_id is None:
        return None

    data = dict(payload or {})

    # Frontend/application aliases -> Supabase V2.
    if "brand" in data and "make" not in data:
        data["make"] = data.pop("brand")

    if "engine" in data and "engine_code" not in data:
        data["engine_code"] = data.pop("engine")

    data["user_id"] = user_id
    data["updated_at"] = now_iso()

    client = get_supabase_client()

    if vehicle_id:
        if not get_vehicle(
            user_id=user_id,
            vehicle_id=vehicle_id,
            include_trashed=True,
        ):
            return None

        response = (
            client.table("vehicles")
            .update(_clean_payload(data))
            .eq("id", vehicle_id)
            .eq("user_id", user_id)
            .execute()
        )
    else:
        data.setdefault("lifecycle_status", "ACTIVE")

        response = (
            client.table("vehicles")
            .insert(_clean_payload(data))
            .execute()
        )

    return _one(response)


def soft_delete_vehicle(
    *,
    user_id: Uuid | None,
    vehicle_id: Uuid | None,
    retention_days: int = 30,
) -> bool:
    if user_id is None or vehicle_id is None:
        return False

    if not get_vehicle(
        user_id=user_id,
        vehicle_id=vehicle_id,
        include_trashed=True,
    ):
        return False

    now = datetime.now(timezone.utc)

    payload = {
        "lifecycle_status": "TRASHED",
        "trashed_at": now.isoformat(),
        "restore_until": (
            now + timedelta(days=retention_days)
        ).isoformat(),
        "updated_at": now.isoformat(),
    }

    response = (
        get_supabase_client()
        .table("vehicles")
        .update(payload)
        .eq("id", vehicle_id)
        .eq("user_id", user_id)
        .execute()
    )

    return bool(rows(response))


def restore_vehicle(
    *,
    user_id: Uuid | None,
    vehicle_id: Uuid | None,
) -> dict[str, Any] | None:
    if user_id is None or vehicle_id is None:
        return None

    payload = {
        "lifecycle_status": "ACTIVE",
        "trashed_at": None,
        "restore_until": None,
        "updated_at": now_iso(),
    }

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


# ---------------------------------------------------------------------------
# Vehicle specifications
# ---------------------------------------------------------------------------


def get_vehicle_specs(
    *,
    user_id: Uuid | None,
    vehicle_id: Uuid | None,
) -> dict[str, Any] | None:
    if not get_vehicle(
        user_id=user_id,
        vehicle_id=vehicle_id,
    ):
        return None

    found = rows(
        get_supabase_client()
        .table("vehicle_specs")
        .select("*")
        .eq("vehicle_id", vehicle_id)
        .order("created_at")
        .execute()
    )

    if not found:
        return None

    # Preserve compatibility with callers expecting one object while
    # keeping the V2 parameter-row structure available.
    return {
        "vehicle_id": vehicle_id,
        "items": found,
    }


def upsert_vehicle_specs(
    *,
    user_id: Uuid | None,
    vehicle_id: Uuid | None,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    if not get_vehicle(
        user_id=user_id,
        vehicle_id=vehicle_id,
    ):
        return None

    if not payload:
        return None

    client = get_supabase_client()

    parameter_key = str(
        payload.get("parameter_key")
        or payload.get("key")
        or ""
    ).strip()

    if not parameter_key:
        # V2 vehicle_specs is a parameter table, not a single wide row.
        # If the caller supplied a generic dictionary, persist each
        # scalar field as its own parameter.
        saved_items: list[dict[str, Any]] = []

        ignored = {
            "id",
            "vehicle_id",
            "created_at",
            "updated_at",
        }

        for key, value in payload.items():
            if key in ignored or value is None:
                continue

            if isinstance(value, (dict, list, tuple, set)):
                continue

            existing = _one(
                client.table("vehicle_specs")
                .select("*")
                .eq("vehicle_id", vehicle_id)
                .eq("parameter_key", str(key))
                .limit(1)
                .execute()
            )

            data = {
                "vehicle_id": vehicle_id,
                "category": "general",
                "parameter_key": str(key),
                "parameter_name": str(key),
                "actual_value": str(value),
                "source_type": "user",
                "updated_at": now_iso(),
            }

            if existing:
                saved = _one(
                    client.table("vehicle_specs")
                    .update(_clean_payload(data))
                    .eq("id", existing["id"])
                    .execute()
                )
            else:
                saved = _one(
                    client.table("vehicle_specs")
                    .insert(_clean_payload(data))
                    .execute()
                )

            if saved:
                saved_items.append(saved)

        if not saved_items:
            return None

        return {
            "vehicle_id": vehicle_id,
            "items": saved_items,
        }

    existing = _one(
        client.table("vehicle_specs")
        .select("*")
        .eq("vehicle_id", vehicle_id)
        .eq("parameter_key", parameter_key)
        .limit(1)
        .execute()
    )

    allowed = {
        "category",
        "parameter_key",
        "parameter_name",
        "recommended_value",
        "recommended_unit",
        "actual_value",
        "actual_unit",
        "source_type",
        "source_reference",
        "metadata",
    }

    data = {
        key: value
        for key, value in payload.items()
        if key in allowed
    }

    data["vehicle_id"] = vehicle_id
    data["parameter_key"] = parameter_key
    data["updated_at"] = now_iso()

    if existing:
        response = (
            client.table("vehicle_specs")
            .update(_clean_payload(data))
            .eq("id", existing["id"])
            .execute()
        )
    else:
        response = (
            client.table("vehicle_specs")
            .insert(_clean_payload(data))
            .execute()
        )

    return _one(response)


# ---------------------------------------------------------------------------
# Conversations and raw messages
# ---------------------------------------------------------------------------


def get_or_create_conversation(
    *,
    user_id: Uuid | None,
    vehicle_id: Uuid | None = None,
    problem_id: Uuid | None = None,
    title: str = "",
    conversation_id: Uuid | None = None,
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

    if vehicle_id is not None:
        if not get_vehicle(
            user_id=user_id,
            vehicle_id=vehicle_id,
        ):
            vehicle_id = None
            problem_id = None

    if problem_id is not None:
        problem = get_problem(
            user_id=user_id,
            problem_id=problem_id,
        )
        if not problem:
            problem_id = None

    payload = {
        "user_id": user_id,
        "vehicle_id": vehicle_id,
        "problem_id": problem_id,
        "conversation_type": (
            "diagnostic"
            if vehicle_id or problem_id
            else "general"
        ),
        "status": "active",
        "context": {
            "initial_text": str(title or "")[:500],
        },
        "started_at": now_iso(),
        "last_message_at": now_iso(),
        "updated_at": now_iso(),
    }

    response = (
        client.table("conversations")
        .insert(_clean_payload(payload))
        .execute()
    )

    created = _one(response)

    if created is None:
        raise SupabaseOperationError(
            "Conversation was not persisted."
        )

    return created


def save_message(
    *,
    user_id: Uuid | None,
    conversation_id: Uuid | None,
    role: str,
    text: str,
    vehicle_id: Uuid | None = None,
    problem_id: Uuid | None = None,
    language: str = "en",
) -> dict[str, Any] | None:
    if (
        user_id is None
        or conversation_id is None
        or not str(text or "").strip()
    ):
        return None

    client = get_supabase_client()

    conversation = _one(
        client.table("conversations")
        .select("*")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )

    if not conversation:
        return None

    metadata: dict[str, Any] = {}

    if vehicle_id is not None:
        metadata["vehicle_id"] = vehicle_id

    if problem_id is not None:
        metadata["problem_id"] = problem_id

    payload = {
        "conversation_id": conversation_id,
        "role": role,
        "content": str(text or "").strip(),
        "language": language or "en",
        "message_type": "text",
        "metadata": metadata,
    }

    saved = _one(
        client.table("messages")
        .insert(_clean_payload(payload))
        .execute()
    )

    if saved is None:
        raise SupabaseOperationError(
            "Message was not persisted."
        )

    client.table("conversations").update(
        {
            "last_message_at": now_iso(),
            "updated_at": now_iso(),
        }
    ).eq(
        "id",
        conversation_id,
    ).eq(
        "user_id",
        user_id,
    ).execute()

    return saved


def recent_conversation_messages(
    *,
    user_id: Uuid | None,
    conversation_id: Uuid | None = None,
    limit: int = 12,
) -> list[dict[str, Any]]:
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

        conversation_id = (
            latest.get("id")
            if latest
            else None
        )

    if conversation_id is None:
        return []

    conversation = _one(
        client.table("conversations")
        .select("id")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )

    if not conversation:
        return []

    found = rows(
        client.table("messages")
        .select("*")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    # Compatibility for code that previously consumed message_text.
    for item in found:
        if "message_text" not in item:
            item["message_text"] = item.get("content", "")

    return list(reversed(found))


# ---------------------------------------------------------------------------
# Problems
# ---------------------------------------------------------------------------


def list_problems(
    *,
    user_id: Uuid | None,
    vehicle_id: Uuid | None = None,
    statuses: tuple[str, ...] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if user_id is None:
        return []

    vehicles_response = (
        get_supabase_client()
        .table("vehicles")
        .select("id")
        .eq("user_id", user_id)
        .execute()
    )

    vehicle_ids = [
        item["id"]
        for item in rows(vehicles_response)
        if item.get("id")
    ]

    if not vehicle_ids:
        return []

    if vehicle_id is not None:
        owned = {
            str(item)
            for item in vehicle_ids
        }

        if str(vehicle_id) not in owned:
            return []

        vehicle_ids = [vehicle_id]

    query = (
        get_supabase_client()
        .table("problems")
        .select("*")
        .in_("vehicle_id", vehicle_ids)
    )

    if statuses:
        query = query.in_(
            "status",
            list(statuses),
        )

    return rows(
        query.order("updated_at", desc=True)
        .limit(limit)
        .execute()
    )


def get_problem(
    *,
    user_id: Uuid | None,
    problem_id: Uuid | None,
) -> dict[str, Any] | None:
    if user_id is None or problem_id is None:
        return None

    problem = _one(
        get_supabase_client()
        .table("problems")
        .select("*")
        .eq("id", problem_id)
        .limit(1)
        .execute()
    )

    if problem is None:
        return None

    vehicle_id = problem.get("vehicle_id")

    if not vehicle_id:
        return None

    vehicle = _one(
        get_supabase_client()
        .table("vehicles")
        .select("id")
        .eq("id", vehicle_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )

    if vehicle is None:
        return None

    return problem


def save_problem(
    *,
    user_id: Uuid | None,
    vehicle_id: Uuid | None,
    payload: dict[str, Any],
    problem_id: Uuid | None = None,
) -> dict[str, Any] | None:
    if user_id is None or vehicle_id is None:
        return None

    if not get_vehicle(
        user_id=user_id,
        vehicle_id=vehicle_id,
    ):
        return None

    base = dict(payload or {})

    base.pop("user_id", None)
    base.pop("last_seen_at", None)

    mileage = base.pop("mileage", None)

    if (
        mileage is not None
        and base.get("mileage_start") is None
    ):
        base["mileage_start"] = mileage

    base["vehicle_id"] = vehicle_id
    base["last_updated_at"] = now_iso()
    base["updated_at"] = now_iso()

    client = get_supabase_client()

    if problem_id:
        existing = get_problem(
            user_id=user_id,
            problem_id=problem_id,
        )

        if not existing:
            return None

        if str(existing.get("vehicle_id")) != str(vehicle_id):
            return None

        response = (
            client.table("problems")
            .update(_clean_payload(base))
            .eq("id", problem_id)
            .eq("vehicle_id", vehicle_id)
            .execute()
        )
    else:
        base.setdefault("status", "OPEN")
        base.setdefault(
            "first_seen_at",
            now_iso(),
        )

        response = (
            client.table("problems")
            .insert(_clean_payload(base))
            .execute()
        )

    return _one(response)


# ---------------------------------------------------------------------------
# Vehicle technical events
# ---------------------------------------------------------------------------


def list_vehicle_events(
    *,
    user_id: Uuid | None,
    vehicle_id: Uuid | None,
    problem_id: Uuid | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    if user_id is None or vehicle_id is None:
        return []

    if not get_vehicle(
        user_id=user_id,
        vehicle_id=vehicle_id,
    ):
        return []

    query = (
        get_supabase_client()
        .table("vehicle_events")
        .select("*")
        .eq("vehicle_id", vehicle_id)
    )

    if problem_id is not None:
        problem = get_problem(
            user_id=user_id,
            problem_id=problem_id,
        )

        if not problem:
            return []

        if str(problem.get("vehicle_id")) != str(vehicle_id):
            return []

        query = query.eq(
            "problem_id",
            problem_id,
        )

    return rows(
        query.order("event_date", desc=True)
        .limit(limit)
        .execute()
    )


def create_vehicle_event(
    *,
    user_id: Uuid | None,
    vehicle_id: Uuid | None,
    problem_id: Uuid | None,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    if user_id is None or vehicle_id is None:
        return None

    if not get_vehicle(
        user_id=user_id,
        vehicle_id=vehicle_id,
    ):
        return None

    if problem_id is not None:
        problem = get_problem(
            user_id=user_id,
            problem_id=problem_id,
        )

        if not problem:
            return None

        if str(problem.get("vehicle_id")) != str(vehicle_id):
            return None

    data = dict(payload or {})

    data.pop("user_id", None)

    occurred_at = data.pop(
        "occurred_at",
        None,
    )

    data["vehicle_id"] = vehicle_id
    data["problem_id"] = problem_id

    data.setdefault(
        "event_date",
        occurred_at or now_iso(),
    )

    return _one(
        get_supabase_client()
        .table("vehicle_events")
        .insert(_clean_payload(data))
        .execute()
    )


# ---------------------------------------------------------------------------
# Search episodes / stages
# ---------------------------------------------------------------------------


def create_search_episode(
    *,
    user_id: Uuid | None,
    vehicle_id: Uuid | None,
    problem_id: Uuid | None,
    reason: str,
) -> dict[str, Any] | None:
    if user_id is None or problem_id is None:
        return None

    problem = get_problem(
        user_id=user_id,
        problem_id=problem_id,
    )

    if not problem:
        return None

    problem_vehicle_id = problem.get("vehicle_id")

    if (
        vehicle_id is not None
        and str(problem_vehicle_id) != str(vehicle_id)
    ):
        return None

    payload = {
        "problem_id": problem_id,
        "status": "RUNNING",
        "current_stage": 1,
        "trigger_type": "diagnostic_search",
        "search_context": {
            "reason": reason,
            "vehicle_id": (
                vehicle_id
                or problem_vehicle_id
            ),
        },
        "started_at": now_iso(),
        "updated_at": now_iso(),
    }

    return _one(
        get_supabase_client()
        .table("search_episodes")
        .insert(_clean_payload(payload))
        .execute()
    )


def update_search_episode(
    *,
    user_id: Uuid | None,
    episode_id: Uuid | None,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    if user_id is None or episode_id is None:
        return None

    client = get_supabase_client()

    episode = _one(
        client.table("search_episodes")
        .select("*")
        .eq("id", episode_id)
        .limit(1)
        .execute()
    )

    if not episode:
        return None

    if not get_problem(
        user_id=user_id,
        problem_id=episode.get("problem_id"),
    ):
        return None

    data = dict(payload or {})
    data.pop("user_id", None)
    data.pop("vehicle_id", None)
    data.pop("reason", None)

    data["updated_at"] = now_iso()

    if data.get("status") in {
        "COMPLETED",
        "INSUFFICIENT_EVIDENCE",
        "FAILED",
    }:
        data.setdefault(
            "completed_at",
            now_iso(),
        )

    return _one(
        client.table("search_episodes")
        .update(_clean_payload(data))
        .eq("id", episode_id)
        .execute()
    )


def create_search_run(
    *,
    user_id: Uuid | None,
    episode_id: Uuid | None,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    if user_id is None or episode_id is None:
        return None

    client = get_supabase_client()

    episode = _one(
        client.table("search_episodes")
        .select("*")
        .eq("id", episode_id)
        .limit(1)
        .execute()
    )

    if not episode:
        return None

    if not get_problem(
        user_id=user_id,
        problem_id=episode.get("problem_id"),
    ):
        return None

    data = dict(payload or {})

    data.pop("user_id", None)

    data["search_episode_id"] = episode_id
    data.setdefault(
        "started_at",
        now_iso(),
    )

    sources_found = data.get(
        "sources_found"
    )

    relevant_sources = data.get(
        "relevant_sources"
    )

    if isinstance(sources_found, list):
        data["sources_found"] = len(
            sources_found
        )

    if isinstance(relevant_sources, list):
        data["relevant_sources"] = len(
            relevant_sources
        )

    if data.get("status") in {
        "COMPLETED",
        "FAILED",
    }:
        data.setdefault(
            "completed_at",
            now_iso(),
        )

    saved = _one(
        client.table("search_runs")
        .insert(_clean_payload(data))
        .execute()
    )

    if saved:
        client.table("search_episodes").update(
            {
                "current_stage": data.get(
                    "stage_number",
                    1,
                ),
                "updated_at": now_iso(),
            }
        ).eq(
            "id",
            episode_id,
        ).execute()

    return saved


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


def upsert_source(
    source: dict[str, Any],
) -> dict[str, Any] | None:
    raw_url = str(
        source.get("url")
        or source.get("canonical_url")
        or ""
    )

    url = canonical_url(raw_url)

    if not url:
        return None

    client = get_supabase_client()

    existing = _one(
        client.table("sources")
        .select("*")
        .eq("url", url)
        .limit(1)
        .execute()
    )

    metadata = dict(
        source.get("metadata")
        if isinstance(
            source.get("metadata"),
            dict,
        )
        else {}
    )

    description = str(
        source.get("description")
        or source.get("snippet")
        or ""
    ).strip()

    if description:
        metadata.setdefault(
            "description",
            description,
        )

    payload = {
        "source_type": str(
            source.get("type")
            or source.get("source_type")
            or "external"
        ).strip(),
        "url": url,
        "title": str(
            source.get("title")
            or url
        ).strip(),
        "domain": str(
            source.get("domain")
            or _source_domain(url)
        ).strip(),
        "author": source.get("author"),
        "publisher": source.get("publisher"),
        "published_at": source.get("published_at"),
        "language": source.get("language"),
        "external_id": source.get("external_id"),
        "trust_level": source.get("trust_level"),
        "status": source.get("status") or "active",
        "metadata": metadata,
        "last_checked_at": now_iso(),
        "updated_at": now_iso(),
    }

    if existing:
        return _one(
            client.table("sources")
            .update(_clean_payload(payload))
            .eq("id", existing["id"])
            .execute()
        )

    payload["first_seen_at"] = now_iso()

    return _one(
        client.table("sources")
        .insert(_clean_payload(payload))
        .execute()
    )


def link_problem_source(
    *,
    user_id: Uuid | None,
    problem_id: Uuid | None,
    source_id: Uuid | None,
    search_run_id: Uuid | None,
    summary: str,
    relevance: float = 0.5,
) -> dict[str, Any] | None:
    if (
        user_id is None
        or problem_id is None
        or source_id is None
    ):
        return None

    if not get_problem(
        user_id=user_id,
        problem_id=problem_id,
    ):
        return None

    discovered_stage = None

    if search_run_id is not None:
        run = _one(
            get_supabase_client()
            .table("search_runs")
            .select("stage_number")
            .eq("id", search_run_id)
            .limit(1)
            .execute()
        )

        if run:
            discovered_stage = run.get(
                "stage_number"
            )

    payload = {
        "problem_id": problem_id,
        "source_id": source_id,
        "relation_type": "diagnostic_evidence",
        "relevance_score": relevance,
        "extracted_evidence": summary,
        "discovered_stage": discovered_stage,
        "metadata": {
            "search_run_id": search_run_id,
        },
    }

    return _one(
        get_supabase_client()
        .table("problem_sources")
        .insert(_clean_payload(payload))
        .execute()
    )


def list_problem_sources(
    *,
    user_id: Uuid | None,
    problem_id: Uuid | None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    if user_id is None or problem_id is None:
        return []

    if not get_problem(
        user_id=user_id,
        problem_id=problem_id,
    ):
        return []

    return rows(
        get_supabase_client()
        .table("problem_sources")
        .select("*, sources(*)")
        .eq("problem_id", problem_id)
        .limit(limit)
        .execute()
    )


# ---------------------------------------------------------------------------
# Internal knowledge
# ---------------------------------------------------------------------------


def find_relevant_knowledge(
    *,
    vehicle: dict[str, Any] | None,
    symptom: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    text = " ".join(
        str(symptom or "").split()
    )

    if not text:
        return []

    client = get_supabase_client()

    query = (
        client.table("knowledge_items")
        .select("*")
        .limit(limit)
    )

    # knowledge_items in V2 is linked to a normalized
    # vehicle_configuration_id. It does not contain legacy
    # vehicle_make / vehicle_model columns, so do not filter
    # against non-existent columns here.

    tokens = [
        part.strip(".,:;!?()[]{}").lower()
        for part in text.split()
        if len(
            part.strip(".,:;!?()[]{}")
        ) >= 5
    ]

    if tokens:
        token = tokens[0]

        query = query.or_(
            f"title.ilike.%{token}%,"
            f"summary.ilike.%{token}%,"
            f"component.ilike.%{token}%"
        )

    return rows(
        query.order(
            "confidence",
            desc=True,
        ).execute()
    )
