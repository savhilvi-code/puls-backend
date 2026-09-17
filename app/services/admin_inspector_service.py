from __future__ import annotations

from typing import Any, Iterable

from fastapi import HTTPException

from app.database.supabase import get_supabase_client, rows


INSPECTOR_TABLES = (
    "conversations",
    "messages",
    "problems",
    "vehicle_events",
    "search_episodes",
    "search_runs",
    "sources",
    "problem_sources",
    "knowledge_items",
    "knowledge_sources",
    "fleet_events",
)


def _safe_page(limit: int, offset: int) -> tuple[int, int]:
    return max(1, min(int(limit), 100)), max(0, int(offset))


def _execute(query: Any, message: str) -> Any:
    try:
        return query.execute()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=message) from exc


def _count_table(table: str) -> int:
    response = _execute(
        get_supabase_client().table(table).select("id", count="exact").limit(1),
        f"Failed to count {table}.",
    )
    count = getattr(response, "count", None)
    return int(count) if count is not None else len(rows(response))


def get_overview() -> dict[str, Any]:
    counts = {table: _count_table(table) for table in INSPECTOR_TABLES}
    recent = _execute(
        get_supabase_client()
        .table("conversations")
        .select("id,title,status,user_id,vehicle_id,problem_id,last_message_at,created_at")
        .order("last_message_at", desc=True)
        .limit(5),
        "Failed to load recent activity.",
    )
    return {"counts": counts, "recent_conversations": rows(recent)}


def _apply_eq(query: Any, filters: dict[str, Any]) -> Any:
    for column, value in filters.items():
        if value is not None and str(value).strip() != "":
            query = query.eq(column, value)
    return query


def _list_rows(
    table: str,
    *,
    limit: int,
    offset: int,
    order_by: str,
    order_desc: bool = True,
    filters: dict[str, Any] | None = None,
    search_column: str | None = None,
    search: str | None = None,
    select: str = "*",
) -> dict[str, Any]:
    limit, offset = _safe_page(limit, offset)
    query = get_supabase_client().table(table).select(select, count="exact")
    query = _apply_eq(query, filters or {})
    if search_column and str(search or "").strip():
        query = query.ilike(search_column, f"%{str(search).strip()}%")
    query = query.order(order_by, desc=order_desc).range(offset, offset + limit - 1)
    response = _execute(query, f"Failed to load {table}.")
    items = rows(response)
    count = getattr(response, "count", None)
    return {
        "items": items,
        "total": int(count) if count is not None else len(items),
        "limit": limit,
        "offset": offset,
    }


def _unique_ids(items: Iterable[dict[str, Any]], field: str) -> list[Any]:
    return list({item.get(field) for item in items if item.get(field) is not None})


def _lookup(table: str, ids: list[Any], columns: str = "*") -> dict[str, dict[str, Any]]:
    if not ids:
        return {}
    response = _execute(
        get_supabase_client().table(table).select(columns).in_("id", ids),
        f"Failed to load related {table}.",
    )
    return {str(row.get("id")): row for row in rows(response)}


def _enrich(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    users = _lookup("users", _unique_ids(items, "user_id"), "id,email,name,full_name")
    vehicles = _lookup(
        "vehicles",
        _unique_ids(items, "vehicle_id"),
        "id,brand,model,generation,year,engine,nickname,vin",
    )
    problems = _lookup(
        "problems",
        _unique_ids(items, "problem_id"),
        "id,title,problem_class,component,status",
    )
    enriched = []
    for item in items:
        row = dict(item)
        row["user"] = users.get(str(item.get("user_id")))
        row["vehicle"] = vehicles.get(str(item.get("vehicle_id")))
        row["problem"] = problems.get(str(item.get("problem_id")))
        enriched.append(row)
    return enriched


def list_conversations(
    *, limit: int, offset: int, status: str | None, search: str | None,
) -> dict[str, Any]:
    page = _list_rows(
        "conversations", limit=limit, offset=offset, order_by="last_message_at",
        filters={"status": status}, search_column="title", search=search,
        select="*,messages(count)",
    )
    items = _enrich(page["items"])
    for item in items:
        embedded = item.pop("messages", [])
        item["message_count"] = (
            int(embedded[0].get("count") or 0)
            if isinstance(embedded, list) and embedded
            else 0
        )
    page["items"] = items
    return page


def list_conversation_messages(conversation_id: int, *, limit: int, offset: int) -> dict[str, Any]:
    return _list_rows(
        "messages", limit=limit, offset=offset, order_by="created_at",
        order_desc=False, filters={"conversation_id": conversation_id},
    )


def list_problems(
    *, limit: int, offset: int, status: str | None, problem_class: str | None,
    search: str | None,
) -> dict[str, Any]:
    page = _list_rows(
        "problems", limit=limit, offset=offset, order_by="updated_at",
        filters={"status": status, "problem_class": problem_class},
        search_column="title", search=search,
    )
    page["items"] = _enrich(page["items"])
    return page


def list_vehicle_events(
    *, limit: int, offset: int, event_type: str | None, search: str | None,
) -> dict[str, Any]:
    page = _list_rows(
        "vehicle_events", limit=limit, offset=offset, order_by="occurred_at",
        filters={"event_type": event_type}, search_column="title", search=search,
    )
    page["items"] = _enrich(page["items"])
    return page


def list_search_episodes(
    *, limit: int, offset: int, status: str | None,
) -> dict[str, Any]:
    page = _list_rows(
        "search_episodes", limit=limit, offset=offset, order_by="created_at",
        filters={"status": status},
    )
    page["items"] = _enrich(page["items"])
    return page


def list_search_runs(search_episode_id: int, *, limit: int, offset: int) -> dict[str, Any]:
    return _list_rows(
        "search_runs", limit=limit, offset=offset, order_by="stage_number",
        order_desc=False, filters={"search_episode_id": search_episode_id},
    )


def list_sources(*, limit: int, offset: int, source_type: str | None, search: str | None) -> dict[str, Any]:
    page = _list_rows(
        "sources", limit=limit, offset=offset, order_by="updated_at",
        filters={"source_type": source_type}, search_column="title", search=search,
    )
    source_ids = _unique_ids(page["items"], "id")
    links: list[dict[str, Any]] = []
    if source_ids:
        response = _execute(
            get_supabase_client().table("problem_sources").select(
                "id,source_id,problem_id,search_run_id,evidence_summary,relevance,created_at"
            ).in_("source_id", source_ids),
            "Failed to load source relations.",
        )
        links = rows(response)
    by_source: dict[str, list[dict[str, Any]]] = {}
    for link in links:
        by_source.setdefault(str(link.get("source_id")), []).append(link)
    for item in page["items"]:
        item["problem_sources"] = by_source.get(str(item.get("id")), [])
    return page


def list_knowledge_items(*, limit: int, offset: int, search: str | None) -> dict[str, Any]:
    page = _list_rows(
        "knowledge_items", limit=limit, offset=offset, order_by="updated_at",
        search_column="title", search=search,
    )
    item_ids = _unique_ids(page["items"], "id")
    links: list[dict[str, Any]] = []
    if item_ids:
        response = _execute(
            get_supabase_client().table("knowledge_sources").select("*").in_(
                "knowledge_item_id", item_ids
            ),
            "Failed to load knowledge source relations.",
        )
        links = rows(response)
    by_item: dict[str, list[dict[str, Any]]] = {}
    for link in links:
        by_item.setdefault(str(link.get("knowledge_item_id")), []).append(link)
    for item in page["items"]:
        item["knowledge_sources"] = by_item.get(str(item.get("id")), [])
    return page


def list_fleet_events(*, limit: int, offset: int, search: str | None) -> dict[str, Any]:
    page = _list_rows(
        "fleet_events", limit=limit, offset=offset, order_by="created_at",
        search_column="symptom_summary", search=search,
    )
    page["items"] = _enrich(page["items"])
    return page


def _rows_for(
    table: str, column: str, value: Any, order_by: str, *, limit: int = 200,
) -> list[dict[str, Any]]:
    response = _execute(
        get_supabase_client().table(table).select("*").eq(column, value).order(
            order_by, desc=False
        ).limit(limit),
        f"Failed to load trace {table}.",
    )
    return rows(response)


def get_problem_trace(problem_id: int) -> dict[str, Any]:
    problem_response = _execute(
        get_supabase_client().table("problems").select("*").eq("id", problem_id).limit(1),
        "Failed to load problem trace.",
    )
    problem_rows = rows(problem_response)
    if not problem_rows:
        raise HTTPException(status_code=404, detail="Problem not found.")
    problem = problem_rows[0]
    vehicle = _lookup("vehicles", [problem.get("vehicle_id")]).get(str(problem.get("vehicle_id")))
    conversations = _rows_for("conversations", "problem_id", problem_id, "created_at")
    messages = _rows_for("messages", "problem_id", problem_id, "created_at")
    conversation_ids = _unique_ids(conversations, "id")
    if conversation_ids:
        conversation_messages = _execute(
            get_supabase_client().table("messages").select("*").in_(
                "conversation_id", conversation_ids
            ).order("created_at", desc=False).limit(200),
            "Failed to load trace conversation messages.",
        )
        by_id = {str(row.get("id")): row for row in messages}
        by_id.update({str(row.get("id")): row for row in rows(conversation_messages)})
        messages = sorted(by_id.values(), key=lambda row: str(row.get("created_at") or ""))
    events = _rows_for("vehicle_events", "problem_id", problem_id, "occurred_at")
    episodes = _rows_for("search_episodes", "problem_id", problem_id, "created_at")
    episode_ids = _unique_ids(episodes, "id")
    runs: list[dict[str, Any]] = []
    if episode_ids:
        run_response = _execute(
            get_supabase_client().table("search_runs").select("*").in_(
                "search_episode_id", episode_ids
            ).order("stage_number", desc=False),
            "Failed to load trace search runs.",
        )
        runs = rows(run_response)
    problem_sources = _rows_for("problem_sources", "problem_id", problem_id, "created_at")
    source_map = _lookup("sources", _unique_ids(problem_sources, "source_id"))
    fleet_events = _rows_for("fleet_events", "source_problem_id", problem_id, "created_at")
    return {
        "problem": problem,
        "vehicle": vehicle,
        "conversations": conversations,
        "messages": messages,
        "vehicle_events": events,
        "search_episodes": episodes,
        "search_runs": runs,
        "problem_sources": problem_sources,
        "sources": list(source_map.values()),
        "fleet_events": fleet_events,
        "knowledge_items": [],
        "limitations": [
            "The current schema has no direct Problem-to-Knowledge Item relation; no inferred relation is shown.",
            "Problem Trace caps each relation at 200 rows to keep the inspector bounded.",
        ],
    }
