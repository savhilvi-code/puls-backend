from __future__ import annotations

from collections import Counter
from typing import Any, Callable, Iterable

from fastapi import HTTPException

from app.database.supabase import get_supabase_client, rows


INSPECTOR_TABLES = (
    "users", "vehicles", "conversations", "messages", "problems",
    "vehicle_events", "search_episodes", "search_runs", "sources",
    "problem_sources", "knowledge_items", "knowledge_sources", "fleet_events",
)
ACTIVE_PROBLEM_STATUSES = ("OPEN", "IN_PROGRESS", "AWAITING_CONFIRMATION")
PROBLEM_STATUSES = (*ACTIVE_PROBLEM_STATUSES, "SOLVED", "CLOSED")
VEHICLE_EVENT_TYPES = (
    "SYMPTOM", "DTC", "CHECK", "REPAIR", "SERVICE",
    "REPLACEMENT", "RESULT", "MILEAGE", "NOTE",
)


def _safe_page(limit: int, offset: int) -> tuple[int, int]:
    return max(1, min(int(limit), 100)), max(0, int(offset))


def _execute(query: Any, message: str) -> Any:
    try:
        return query.execute()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=message) from exc


def _error_text(exc: Exception) -> str:
    return str(getattr(exc, "detail", None) or exc or "Unavailable")


def _optional(operation: Callable[[], Any], label: str) -> tuple[Any, str | None]:
    try:
        return operation(), None
    except Exception as exc:
        return None, f"{label}: {_error_text(exc)}"


def _count_query(query: Any, message: str) -> int:
    response = _execute(query.select("id", count="exact").limit(1), message)
    count = getattr(response, "count", None)
    return int(count) if count is not None else len(rows(response))


def _count_table(table: str) -> int:
    return _count_query(
        get_supabase_client().table(table), f"Failed to count {table}."
    )


def _count_filtered(table: str, column: str, values: Iterable[str]) -> int:
    values = list(values)
    query = get_supabase_client().table(table)
    query = query.eq(column, values[0]) if len(values) == 1 else query.in_(column, values)
    return _count_query(query, f"Failed to count {table} by {column}.")


def _recent_rows(
    table: str, order_columns: tuple[str, ...], limit: int = 5,
) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for column in order_columns:
        try:
            response = (
                get_supabase_client().table(table).select("*")
                .order(column, desc=True).limit(limit).execute()
            )
            return rows(response)
        except Exception as exc:
            last_error = exc
    raise HTTPException(
        status_code=503, detail=f"Failed to load recent {table}."
    ) from last_error


def _value_distribution(
    table: str, column: str, *, max_rows: int = 5000,
) -> dict[str, int]:
    found: list[dict[str, Any]] = []
    offset = 0
    page_size = 1000
    while offset < max_rows:
        response = _execute(
            get_supabase_client().table(table).select(column).range(
                offset, min(offset + page_size - 1, max_rows - 1)
            ),
            f"Failed to load {table} distribution.",
        )
        batch = rows(response)
        found.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    if len(found) >= max_rows:
        raise HTTPException(
            status_code=503,
            detail=f"{table} distribution exceeds the bounded inspector limit.",
        )
    return dict(sorted(Counter(str(row.get(column) or "UNKNOWN") for row in found).items()))


def get_overview() -> dict[str, Any]:
    counts: dict[str, int | None] = {}
    errors: dict[str, str] = {}
    for table in INSPECTOR_TABLES:
        value, error = _optional(lambda table=table: _count_table(table), f"count.{table}")
        counts[table] = value
        if error:
            errors[f"count.{table}"] = error

    active, error = _optional(
        lambda: _count_filtered("problems", "status", ACTIVE_PROBLEM_STATUSES),
        "metric.active_problems",
    )
    if error:
        errors["metric.active_problems"] = error

    problem_status: dict[str, int | None] = {}
    for status in PROBLEM_STATUSES:
        value, status_error = _optional(
            lambda status=status: _count_filtered("problems", "status", [status]),
            f"distribution.problem_status.{status}",
        )
        problem_status[status] = value
        if status_error:
            errors[f"distribution.problem_status.{status}"] = status_error

    event_types: dict[str, int | None] = {}
    for event_type in VEHICLE_EVENT_TYPES:
        value, type_error = _optional(
            lambda event_type=event_type: _count_filtered(
                "vehicle_events", "event_type", [event_type]
            ),
            f"distribution.vehicle_event_type.{event_type}",
        )
        event_types[event_type] = value
        if type_error:
            errors[f"distribution.vehicle_event_type.{event_type}"] = type_error

    source_types, source_error = _optional(
        lambda: _value_distribution("sources", "source_type"),
        "distribution.source_type",
    )
    if source_error:
        errors["distribution.source_type"] = source_error

    recent_specs = {
        "conversations": ("last_message_at", "updated_at", "started_at"),
        "problems": ("last_updated_at", "updated_at", "first_seen_at"),
        "search_episodes": ("updated_at", "started_at"),
        "knowledge_items": ("updated_at", "created_at"),
    }
    recent: dict[str, list[dict[str, Any]] | None] = {}
    for table, order_columns in recent_specs.items():
        value, recent_error = _optional(
            lambda table=table, order_columns=order_columns: _recent_rows(
                table, order_columns
            ),
            f"recent.{table}",
        )
        recent[table] = value
        if recent_error:
            errors[f"recent.{table}"] = recent_error

    return {
        "counts": counts,
        "metrics": {
            "users": counts.get("users"),
            "vehicles": counts.get("vehicles"),
            "conversations": counts.get("conversations"),
            "messages": counts.get("messages"),
            "active_problems": active,
            "vehicle_events": counts.get("vehicle_events"),
            "search_episodes": counts.get("search_episodes"),
            "search_runs": counts.get("search_runs"),
            "sources": counts.get("sources"),
            "knowledge_items": counts.get("knowledge_items"),
        },
        "distributions": {
            "data_volume": {
                key: counts.get(key)
                for key in (
                    "messages", "problems", "vehicle_events",
                    "search_runs", "sources", "knowledge_items",
                )
            },
            "problem_status": problem_status,
            "vehicle_event_type": event_types,
            "source_type": source_types,
        },
        "recent": recent,
        "errors": errors,
    }


def _apply_eq(query: Any, filters: dict[str, Any]) -> Any:
    for column, value in filters.items():
        if value is not None and str(value).strip() != "":
            query = query.eq(column, value)
    return query


def _list_rows(
    table: str, *, limit: int, offset: int, order_by: str | None,
    order_desc: bool = True, filters: dict[str, Any] | None = None,
    search_column: str | None = None, search: str | None = None,
) -> dict[str, Any]:
    limit, offset = _safe_page(limit, offset)
    query = get_supabase_client().table(table).select("*", count="exact")
    query = _apply_eq(query, filters or {})
    if search_column and str(search or "").strip():
        query = query.ilike(search_column, f"%{str(search).strip()}%")
    if order_by:
        query = query.order(order_by, desc=order_desc)
    response = _execute(
        query.range(offset, offset + limit - 1), f"Failed to load {table}."
    )
    items = rows(response)
    count = getattr(response, "count", None)
    return {
        "items": items,
        "total": int(count) if count is not None else len(items),
        "limit": limit,
        "offset": offset,
        "warnings": [],
    }


def _unique_ids(items: Iterable[dict[str, Any]], field: str) -> list[Any]:
    return list({item.get(field) for item in items if item.get(field) is not None})


def _lookup_optional(
    table: str, ids: list[Any], *, label: str,
) -> tuple[dict[str, dict[str, Any]], str | None]:
    if not ids:
        return {}, None
    try:
        response = get_supabase_client().table(table).select("*").in_("id", ids).execute()
        return {str(row.get("id")): row for row in rows(response)}, None
    except Exception:
        return {}, f"Related {label} metadata is unavailable; primary rows are still shown."


def _enrich(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    users, error = _lookup_optional("users", _unique_ids(items, "user_id"), label="user")
    if error:
        warnings.append(error)
    vehicles, error = _lookup_optional(
        "vehicles", _unique_ids(items, "vehicle_id"), label="vehicle"
    )
    if error:
        warnings.append(error)
    problems, error = _lookup_optional(
        "problems", _unique_ids(items, "problem_id"), label="problem"
    )
    if error:
        warnings.append(error)
    enriched = []
    for item in items:
        row = dict(item)
        row["user"] = users.get(str(item.get("user_id")))
        row["vehicle"] = vehicles.get(str(item.get("vehicle_id")))
        row["problem"] = problems.get(str(item.get("problem_id")))
        enriched.append(row)
    return enriched, list(dict.fromkeys(warnings))


def _attach_enrichment(page: dict[str, Any]) -> dict[str, Any]:
    page["items"], warnings = _enrich(page["items"])
    page["warnings"].extend(warnings)
    return page


def list_conversations(
    *, limit: int, offset: int, status: str | None, search: str | None,
) -> dict[str, Any]:
    page = _list_rows(
        "conversations", limit=limit, offset=offset, order_by="last_message_at",
        filters={"status": status}, search_column="context->>initial_text", search=search,
    )
    page = _attach_enrichment(page)
    for item in page["items"]:
        count, error = _optional(
            lambda item=item: _count_filtered(
                "messages", "conversation_id", [str(item.get("id"))]
            ),
            f"messages for conversation {item.get('id')}",
        )
        item["message_count"] = count
        if error:
            page["warnings"].append(error)
    page["warnings"] = list(dict.fromkeys(page["warnings"]))
    return page


def list_conversation_messages(
    conversation_id: str, *, limit: int, offset: int,
) -> dict[str, Any]:
    return _list_rows(
        "messages", limit=limit, offset=offset, order_by="created_at",
        order_desc=False, filters={"conversation_id": conversation_id},
    )


def list_problems(
    *, limit: int, offset: int, status: str | None, problem_class: str | None,
    search: str | None,
) -> dict[str, Any]:
    return _attach_enrichment(_list_rows(
        "problems", limit=limit, offset=offset, order_by="updated_at",
        filters={"status": status, "problem_class": problem_class},
        search_column="title", search=search,
    ))


def list_vehicle_events(
    *, limit: int, offset: int, event_type: str | None, search: str | None,
) -> dict[str, Any]:
    return _attach_enrichment(_list_rows(
        "vehicle_events", limit=limit, offset=offset, order_by="event_date",
        filters={"event_type": event_type}, search_column="title", search=search,
    ))


def list_search_episodes(
    *, limit: int, offset: int, status: str | None,
) -> dict[str, Any]:
    page = _list_rows(
        "search_episodes", limit=limit, offset=offset, order_by="started_at",
        filters={"status": status},
    )
    problems, error = _lookup_optional(
        "problems", _unique_ids(page["items"], "problem_id"), label="problem"
    )
    if error:
        page["warnings"].append(error)
    vehicles, vehicle_error = _lookup_optional(
        "vehicles",
        [row.get("vehicle_id") for row in problems.values() if row.get("vehicle_id")],
        label="vehicle",
    )
    if vehicle_error:
        page["warnings"].append(vehicle_error)
    for item in page["items"]:
        problem = problems.get(str(item.get("problem_id")))
        item["problem"] = problem
        item["vehicle"] = vehicles.get(str((problem or {}).get("vehicle_id")))
    return page


def list_search_runs(
    search_episode_id: str, *, limit: int, offset: int,
) -> dict[str, Any]:
    return _list_rows(
        "search_runs", limit=limit, offset=offset, order_by="stage_number",
        order_desc=False, filters={"search_episode_id": search_episode_id},
    )


def list_sources(
    *, limit: int, offset: int, source_type: str | None, search: str | None,
) -> dict[str, Any]:
    page = _list_rows(
        "sources", limit=limit, offset=offset, order_by="updated_at",
        filters={"source_type": source_type}, search_column="title", search=search,
    )
    source_ids = _unique_ids(page["items"], "id")
    links: list[dict[str, Any]] = []
    if source_ids:
        try:
            response = (
                get_supabase_client().table("problem_sources").select("*")
                .in_("source_id", source_ids).limit(500).execute()
            )
            links = rows(response)
        except Exception:
            page["warnings"].append(
                "Problem-source relations are unavailable; source rows are still shown."
            )
    by_source: dict[str, list[dict[str, Any]]] = {}
    for link in links:
        by_source.setdefault(str(link.get("source_id")), []).append(link)
    for item in page["items"]:
        item["problem_sources"] = by_source.get(str(item.get("id")), [])
    return page


def list_knowledge_items(
    *, limit: int, offset: int, search: str | None,
) -> dict[str, Any]:
    page = _list_rows(
        "knowledge_items", limit=limit, offset=offset, order_by="updated_at",
        search_column="title", search=search,
    )
    item_ids = _unique_ids(page["items"], "id")
    links: list[dict[str, Any]] = []
    if item_ids:
        try:
            response = (
                get_supabase_client().table("knowledge_sources").select("*")
                .in_("knowledge_item_id", item_ids).limit(500).execute()
            )
            links = rows(response)
        except Exception:
            page["warnings"].append(
                "Knowledge-source relations are unavailable; knowledge rows are still shown."
            )
    by_item: dict[str, list[dict[str, Any]]] = {}
    for link in links:
        by_item.setdefault(str(link.get("knowledge_item_id")), []).append(link)
    for item in page["items"]:
        item["knowledge_sources"] = by_item.get(str(item.get("id")), [])
    return page


def list_fleet_events(
    *, limit: int, offset: int, search: str | None,
) -> dict[str, Any]:
    return _attach_enrichment(_list_rows(
        "fleet_events", limit=limit, offset=offset, order_by="created_at",
        search_column="symptom_summary", search=search,
    ))


def _rows_for(
    table: str, column: str, value: Any, order_by: str | None, *, limit: int = 200,
) -> list[dict[str, Any]]:
    query = get_supabase_client().table(table).select("*").eq(column, value)
    if order_by:
        query = query.order(order_by, desc=False)
    return rows(_execute(query.limit(limit), f"Failed to load trace {table}."))


def get_problem_trace(problem_id: str) -> dict[str, Any]:
    response = _execute(
        get_supabase_client().table("problems").select("*").eq(
            "id", problem_id
        ).limit(1),
        "Failed to load problem trace.",
    )
    found = rows(response)
    if not found:
        raise HTTPException(status_code=404, detail="Problem not found.")
    problem = found[0]
    warnings: list[str] = []
    vehicles, error = _lookup_optional(
        "vehicles", [problem.get("vehicle_id")], label="vehicle"
    )
    if error:
        warnings.append(error)
    vehicle = vehicles.get(str(problem.get("vehicle_id")))

    def trace_rows(table: str, column: str, order_by: str | None) -> list[dict[str, Any]]:
        value, trace_error = _optional(
            lambda: _rows_for(table, column, problem_id, order_by), f"trace.{table}"
        )
        if trace_error:
            warnings.append(trace_error)
        return value or []

    conversations = trace_rows("conversations", "problem_id", "started_at")
    conversation_ids = _unique_ids(conversations, "id")
    messages: list[dict[str, Any]] = []
    if conversation_ids:
        value, message_error = _optional(
            lambda: rows(
                get_supabase_client().table("messages").select("*").in_(
                    "conversation_id", conversation_ids
                ).order("created_at", desc=False).limit(200).execute()
            ),
            "trace.messages",
        )
        messages = value or []
        if message_error:
            warnings.append(message_error)
    events = trace_rows("vehicle_events", "problem_id", "event_date")
    episodes = trace_rows("search_episodes", "problem_id", "started_at")
    episode_ids = _unique_ids(episodes, "id")
    runs: list[dict[str, Any]] = []
    if episode_ids:
        value, run_error = _optional(
            lambda: rows(
                get_supabase_client().table("search_runs").select("*").in_(
                    "search_episode_id", episode_ids
                ).order("stage_number", desc=False).limit(200).execute()
            ),
            "trace.search_runs",
        )
        runs = value or []
        if run_error:
            warnings.append(run_error)
    problem_sources = trace_rows("problem_sources", "problem_id", None)
    sources, source_error = _lookup_optional(
        "sources", _unique_ids(problem_sources, "source_id"), label="source"
    )
    if source_error:
        warnings.append(source_error)
    fleet_events = trace_rows("fleet_events", "source_problem_id", "created_at")
    return {
        "problem": problem,
        "vehicle": vehicle,
        "conversations": conversations,
        "messages": messages,
        "vehicle_events": events,
        "search_episodes": episodes,
        "search_runs": runs,
        "problem_sources": problem_sources,
        "sources": list(sources.values()),
        "fleet_events": fleet_events,
        "knowledge_items": [],
        "warnings": list(dict.fromkeys(warnings)),
        "limitations": [
            "The current schema has no direct Problem-to-Knowledge Item relation; no inferred relation is shown.",
            "Problem Trace caps each relation at 200 rows to keep the inspector bounded.",
        ],
    }
