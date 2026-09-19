from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.database.supabase import get_supabase_client, rows


def _execute(query: Any, message: str) -> Any:
    try:
        return query.execute()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=message) from exc


def _one(table: str, row_id: str, *, required: bool = True) -> dict[str, Any] | None:
    response = _execute(
        get_supabase_client().table(table).select("*").eq("id", row_id).limit(1),
        f"Failed to load {table} row.",
    )
    found = rows(response)
    if found:
        return found[0]
    if required:
        raise HTTPException(status_code=404, detail=f"{table} row not found.")
    return None


def _ids_eq(table: str, column: str, value: Any) -> list[Any]:
    response = _execute(
        get_supabase_client().table(table).select("id").eq(column, value).limit(5000),
        f"Failed to inspect related {table} rows.",
    )
    return [row["id"] for row in rows(response) if row.get("id") is not None]


def _ids_in(table: str, column: str, values: list[Any]) -> list[Any]:
    if not values:
        return []
    response = _execute(
        get_supabase_client().table(table).select("id").in_(column, values).limit(5000),
        f"Failed to inspect related {table} rows.",
    )
    return [row["id"] for row in rows(response) if row.get("id") is not None]


def _rows_in(table: str, columns: str, column: str, values: list[Any]) -> list[dict[str, Any]]:
    if not values:
        return []
    response = _execute(
        get_supabase_client().table(table).select(columns).in_(column, values).limit(5000),
        f"Failed to inspect related {table} rows.",
    )
    return rows(response)


def _ids_metadata_eq(table: str, key: str, value: Any) -> list[Any]:
    response = _execute(
        get_supabase_client().table(table).select("id").eq(f"metadata->>{key}", str(value)).limit(5000),
        f"Failed to inspect related {table} metadata.",
    )
    return [row["id"] for row in rows(response) if row.get("id") is not None]


def _matching_configurations(vehicle: dict[str, Any]) -> list[dict[str, Any]]:
    make = str(vehicle.get("make") or vehicle.get("brand") or "").strip()
    model = str(vehicle.get("model") or "").strip()
    if not make or not model:
        return []
    response = _execute(
        get_supabase_client().table("vehicle_configurations").select("*").ilike("make", make).ilike("model", model).limit(5000),
        "Failed to inspect shared vehicle configurations.",
    )
    candidates = rows(response)
    year = vehicle.get("year")
    if year not in (None, ""):
        year = int(year)
        candidates = [
            item for item in candidates
            if (item.get("year_from") is None or int(item["year_from"]) <= year)
            and (item.get("year_to") is None or int(item["year_to"]) >= year)
        ]
    return candidates


def _delete_ids(table: str, ids: list[Any]) -> None:
    if not ids:
        return
    _execute(
        get_supabase_client().table(table).delete().in_("id", ids),
        f"Failed to delete {table} rows.",
    )


def _delete_id(table: str, row_id: str) -> None:
    _execute(
        get_supabase_client().table(table).delete().eq("id", row_id),
        f"Failed to delete {table} row.",
    )


def _source_summary(knowledge_item_ids: list[Any]) -> dict[str, Any]:
    links = _rows_in("knowledge_sources", "id,knowledge_item_id,source_id", "knowledge_item_id", knowledge_item_ids)
    source_ids = list({row.get("source_id") for row in links if row.get("source_id") is not None})
    shared_links = _rows_in("knowledge_sources", "knowledge_item_id,source_id", "source_id", source_ids)
    problem_links = _rows_in("problem_sources", "problem_id,source_id", "source_id", source_ids)
    selected = {str(value) for value in knowledge_item_ids}
    shared_source_ids = {
        str(row.get("source_id")) for row in shared_links
        if str(row.get("knowledge_item_id")) not in selected
    }
    shared_source_ids.update(str(row.get("source_id")) for row in problem_links)
    return {
        "knowledge_source_links": len(links),
        "source_ids": source_ids,
        "sources_preserved": len(source_ids),
        "shared_sources": len(shared_source_ids),
    }


def preview_vehicle_delete(vehicle_id: str) -> dict[str, Any]:
    vehicle = _one("vehicles", vehicle_id)
    spec_ids = _ids_eq("vehicle_specs", "vehicle_id", vehicle_id)
    problem_ids = _ids_eq("problems", "vehicle_id", vehicle_id)
    event_ids = _ids_eq("vehicle_events", "vehicle_id", vehicle_id)
    conversation_ids = _ids_eq("conversations", "vehicle_id", vehicle_id)
    problem_source_ids = _ids_in("problem_sources", "problem_id", problem_ids)
    episode_ids = _ids_in("search_episodes", "problem_id", problem_ids)
    run_ids = _ids_in("search_runs", "search_episode_id", episode_ids)
    message_ids = _ids_in("messages", "conversation_id", conversation_ids)
    fleet_case_ids = _ids_in("fleet_events", "origin_event_id", event_ids)
    case_knowledge_ids: list[Any] = []
    for case_id in fleet_case_ids:
        case_knowledge_ids.extend(_ids_metadata_eq("knowledge_items", "origin_fleet_event_id", case_id))
    configurations = _matching_configurations(vehicle or {})
    configuration_ids = [row.get("id") for row in configurations if row.get("id") is not None]
    config_knowledge_ids = _ids_in("knowledge_items", "vehicle_configuration_id", configuration_ids)
    config_case_ids = _ids_in("fleet_events", "vehicle_configuration_id", configuration_ids)
    counts = {
        "vehicles": 1,
        "vehicle_specs": len(spec_ids),
        "problems": len(problem_ids),
        "problem_sources": len(problem_source_ids),
        "vehicle_events": len(event_ids),
        "conversations": len(conversation_ids),
        "messages": len(message_ids),
        "search_episodes": len(episode_ids),
        "search_runs": len(run_ids),
        "matching_shared_vehicle_configurations": len(configuration_ids),
        "fleet_cases_detached_from_origin": len(fleet_case_ids),
        "knowledge_items_via_cases_preserved": len(set(case_knowledge_ids)),
        "knowledge_items_via_shared_configurations": len(config_knowledge_ids),
        "fleet_events_via_shared_configurations": len(config_case_ids),
    }
    return {
        "target_type": "VEHICLE", "target_id": vehicle_id,
        "target_label": " ".join(str(value) for value in (vehicle.get("make"), vehicle.get("model"), vehicle.get("year")) if value),
        "counts": counts,
        "effects": {
            "delete": ["vehicles", "vehicle_specs", "problems", "problem_sources", "search_episodes", "search_runs", "vehicle_events"],
            "detach": ["conversations.vehicle_id", "fleet_events.origin_event_id"],
            "preserve": ["conversations", "messages", "vehicle_configurations", "fleet_events", "knowledge_items", "sources", "storage objects"],
        },
        "storage": {
            "photo_url": vehicle.get("photo_url"),
            "action": "PRESERVE",
            "reason": "Admin database deletion does not perform a non-transactional Storage object deletion.",
        },
        "fk_basis": {
            "vehicle_specs": "CASCADE", "problems": "CASCADE", "vehicle_events": "CASCADE",
            "conversations": "SET NULL", "vehicle_configurations": "NO DIRECT FK",
            "fleet_events.origin_event_id": "SET NULL",
        },
    }


def delete_vehicle(vehicle_id: str) -> dict[str, Any]:
    preview = preview_vehicle_delete(vehicle_id)
    _delete_id("vehicles", vehicle_id)
    verification = {
        "vehicle": _one("vehicles", vehicle_id, required=False) is None,
        "vehicle_specs": not _ids_eq("vehicle_specs", "vehicle_id", vehicle_id),
        "problems": not _ids_eq("problems", "vehicle_id", vehicle_id),
        "vehicle_events": not _ids_eq("vehicle_events", "vehicle_id", vehicle_id),
        "conversations_detached": not _ids_eq("conversations", "vehicle_id", vehicle_id),
    }
    if not all(verification.values()):
        raise HTTPException(status_code=500, detail="Vehicle deletion verification failed.")
    return {"deleted": True, "target_type": "VEHICLE", "target_id": vehicle_id, "verification": verification, "preview": preview}


def preview_knowledge_delete(item_id: str) -> dict[str, Any]:
    item = _one("knowledge_items", item_id)
    sources = _source_summary([item_id])
    return {
        "target_type": "KNOWLEDGE_MATERIAL", "target_id": item_id,
        "target_label": item.get("title") or f"Knowledge #{item_id}",
        "counts": {
            "knowledge_items": 1,
            "knowledge_sources": sources["knowledge_source_links"],
            "sources_preserved": sources["sources_preserved"],
            "shared_sources": sources["shared_sources"],
        },
        "effects": {
            "delete": ["knowledge_items", "knowledge_sources"],
            "detach": [],
            "preserve": ["sources", "problem_sources", "storage objects"],
        },
        "source_ids": sources["source_ids"],
    }


def delete_knowledge_material(item_id: str) -> dict[str, Any]:
    preview = preview_knowledge_delete(item_id)
    source_ids = preview.get("source_ids") or []
    _delete_id("knowledge_items", item_id)
    item_gone = _one("knowledge_items", item_id, required=False) is None
    links_gone = not _ids_eq("knowledge_sources", "knowledge_item_id", item_id)
    sources_remaining = len(_rows_in("sources", "id", "id", source_ids)) == len(source_ids)
    verification = {"knowledge_item": item_gone, "knowledge_sources": links_gone, "sources_preserved": sources_remaining}
    if not all(verification.values()):
        raise HTTPException(status_code=500, detail="Knowledge material deletion verification failed.")
    return {"deleted": True, "target_type": "KNOWLEDGE_MATERIAL", "target_id": item_id, "verification": verification, "preview": preview}


def preview_successful_case_delete(case_id: str) -> dict[str, Any]:
    case = _one("fleet_events", case_id)
    knowledge_item_ids = _ids_metadata_eq("knowledge_items", "origin_fleet_event_id", case_id)
    sources = _source_summary(knowledge_item_ids)
    symptoms = case.get("symptoms") if isinstance(case.get("symptoms"), list) else []
    return {
        "target_type": "SUCCESSFUL_CASE", "target_id": case_id,
        "target_label": (str(symptoms[0]).strip() if symptoms else None) or case.get("cause") or f"Successful Case #{case_id}",
        "counts": {
            "fleet_events": 1,
            "promoted_knowledge_items": len(knowledge_item_ids),
            "knowledge_sources": sources["knowledge_source_links"],
            "sources_preserved": sources["sources_preserved"],
            "shared_sources": sources["shared_sources"],
            "origin_vehicle_events_preserved": 1 if case.get("origin_event_id") else 0,
            "vehicle_configurations_preserved": 1 if case.get("vehicle_configuration_id") else 0,
        },
        "effects": {
            "delete": ["fleet_events", "promoted knowledge_items", "their knowledge_sources"],
            "detach": [],
            "preserve": ["sources", "problem_sources", "origin vehicle_event", "vehicle_configuration", "storage objects"],
        },
        "knowledge_item_ids": knowledge_item_ids,
        "source_ids": sources["source_ids"],
    }


def delete_successful_case(case_id: str) -> dict[str, Any]:
    preview = preview_successful_case_delete(case_id)
    knowledge_item_ids = preview.get("knowledge_item_ids") or []
    source_ids = preview.get("source_ids") or []
    _delete_ids("knowledge_items", knowledge_item_ids)
    _delete_id("fleet_events", case_id)
    case_gone = _one("fleet_events", case_id, required=False) is None
    items_gone = not _ids_metadata_eq("knowledge_items", "origin_fleet_event_id", case_id)
    links_gone = not _ids_in("knowledge_sources", "knowledge_item_id", knowledge_item_ids)
    sources_remaining = len(_rows_in("sources", "id", "id", source_ids)) == len(source_ids)
    verification = {
        "fleet_event": case_gone, "promoted_knowledge_items": items_gone,
        "knowledge_sources": links_gone, "sources_preserved": sources_remaining,
    }
    if not all(verification.values()):
        raise HTTPException(status_code=500, detail="Successful case deletion verification failed.")
    return {"deleted": True, "target_type": "SUCCESSFUL_CASE", "target_id": case_id, "verification": verification, "preview": preview}
