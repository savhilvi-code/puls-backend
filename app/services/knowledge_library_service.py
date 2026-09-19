from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from app.database.supabase import get_supabase_client, rows
from app.services.v2_repository import upsert_source


KNOWLEDGE_TYPES = (
    "MANUAL", "MANUFACTURER_DOCUMENT", "TECHNICAL_BULLETIN", "SPECIFICATION",
    "PROCEDURE", "DIAGNOSTIC_REFERENCE", "VIDEO", "FORUM", "ARTICLE",
    "SUCCESSFUL_CASE", "GENERAL", "OTHER",
)
REVIEW_STATUSES = ("PENDING_REVIEW", "VERIFIED", "NEEDS_CLARIFICATION", "REJECTED")
SOURCE_TYPES = ("MANUFACTURER", "MANUAL", "FORUM", "WEBSITE", "YOUTUBE", "SOCIAL", "DOCUMENT", "PULS", "OTHER")
KNOWLEDGE_TYPE_TO_DB = {
    "MANUAL": "MANUAL", "MANUFACTURER_DOCUMENT": "MANUFACTURER",
    "TECHNICAL_BULLETIN": "MANUFACTURER", "SPECIFICATION": "TECHNICAL_REFERENCE",
    "PROCEDURE": "TECHNICAL_REFERENCE", "DIAGNOSTIC_REFERENCE": "TECHNICAL_REFERENCE",
    "VIDEO": "VIDEO", "FORUM": "FORUM_CASE", "ARTICLE": "TECHNICAL_REFERENCE",
    "SUCCESSFUL_CASE": "PULS_CASE", "GENERAL": "TECHNICAL_REFERENCE", "OTHER": "OTHER",
}
DB_TYPE_TO_KNOWLEDGE = {
    "MANUFACTURER": "MANUFACTURER_DOCUMENT", "MANUAL": "MANUAL", "FORUM_CASE": "FORUM",
    "PULS_CASE": "SUCCESSFUL_CASE", "VIDEO": "VIDEO", "TECHNICAL_REFERENCE": "DIAGNOSTIC_REFERENCE", "OTHER": "OTHER",
}
REVIEW_STATUS_TO_DB = {
    "PENDING_REVIEW": "UNVERIFIED", "NEEDS_CLARIFICATION": "SUPPORTED",
    "VERIFIED": "VERIFIED", "REJECTED": "REJECTED",
}
DB_STATUS_TO_REVIEW = {value: key for key, value in REVIEW_STATUS_TO_DB.items()}
CATEGORY_DB_TYPES = {
    "manuals": ("MANUAL", "MANUFACTURER"), "videos": ("VIDEO",),
    "forums": ("FORUM_CASE",), "successful-cases": ("PULS_CASE",),
}
CONFIG_FIELDS = (
    "make", "model", "generation", "year_from", "year_to", "body_type",
    "engine_code", "transmission", "drivetrain", "market",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _page(limit: int, offset: int) -> tuple[int, int]:
    return max(1, min(int(limit), 100)), max(0, int(offset))


def _execute(query: Any, message: str) -> Any:
    try:
        return query.execute()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=message) from exc


def _one(response: Any) -> dict[str, Any] | None:
    found = rows(response)
    return found[0] if found else None


def _text(value: Any) -> str | None:
    value = str(value or "").strip()
    return value or None


def _enum(value: Any, allowed: tuple[str, ...], field: str, default: str | None = None) -> str | None:
    normalized = str(value or default or "").strip().upper()
    if not normalized and default is None:
        return None
    if normalized not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported {field}: {normalized}.")
    return normalized


def _metadata(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _config_payload(applicability: dict[str, Any] | None) -> dict[str, Any]:
    source = applicability if isinstance(applicability, dict) else {}
    payload = {
        "make": _text(source.get("make")),
        "model": _text(source.get("model")),
        "generation": _text(source.get("generation")),
        "year_from": source.get("year_from"),
        "year_to": source.get("year_to"),
        "body_type": _text(source.get("body_type") or source.get("body_chassis")),
        "engine_code": _text(source.get("engine_code") or source.get("engine")),
        "transmission": _text(source.get("transmission")),
        "drivetrain": _text(source.get("drivetrain")),
        "market": _text(source.get("market") or source.get("region")),
    }
    for field in ("year_from", "year_to"):
        if payload[field] not in (None, ""):
            try:
                payload[field] = int(payload[field])
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=f"{field} must be a year.") from exc
    if payload["year_from"] and payload["year_to"] and payload["year_from"] > payload["year_to"]:
        raise HTTPException(status_code=400, detail="year_from must not exceed year_to.")
    return payload


def find_or_create_configuration(applicability: dict[str, Any] | None) -> dict[str, Any] | None:
    payload = _config_payload(applicability)
    if not payload["make"] and not payload["model"]:
        return None
    if not payload["make"] or not payload["model"]:
        raise HTTPException(status_code=400, detail="Vehicle knowledge requires both make and model.")
    client = get_supabase_client()
    query = client.table("vehicle_configurations").select("*")
    for field in CONFIG_FIELDS:
        value = payload.get(field)
        query = query.eq(field, value) if value is not None else query.is_(field, "null")
    existing = _one(_execute(query.limit(1), "Failed to resolve vehicle applicability."))
    if existing:
        return existing
    return _one(_execute(
        client.table("vehicle_configurations").insert(payload),
        "Failed to create vehicle applicability.",
    ))


def _provenance(source_type: str | None, knowledge_type: str) -> str:
    if knowledge_type == "SUCCESSFUL_CASE":
        return "SUCCESSFUL_USER_CASE"
    return {
        "MANUFACTURER": "MANUFACTURER",
        "MANUAL": "MANUAL",
        "FORUM": "FORUM_COMMUNITY",
        "PULS": "MECHANIC_VERIFIED",
    }.get(str(source_type or "").upper(), "EXTERNAL_WEB")


def build_material_payload(data: dict[str, Any], *, existing: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    current = dict(existing or {})
    title = _text(data.get("title") if "title" in data else current.get("title"))
    if not title:
        raise HTTPException(status_code=400, detail="Title is required.")
    current_metadata = _metadata(current.get("metadata"))
    knowledge_type = _enum(
        data.get("knowledge_type") if "knowledge_type" in data else (current_metadata.get("material_type") or DB_TYPE_TO_KNOWLEDGE.get(current.get("knowledge_type"), current.get("knowledge_type"))),
        KNOWLEDGE_TYPES, "knowledge_type", "OTHER",
    )
    status = _enum(
        data.get("validation_status") if "validation_status" in data else (current_metadata.get("review_status") or DB_STATUS_TO_REVIEW.get(current.get("validation_status"), current.get("validation_status"))),
        REVIEW_STATUSES, "validation_status", "PENDING_REVIEW",
    )
    source_type = _enum(data.get("source_type"), SOURCE_TYPES, "source_type")
    applicability = data.get("applicability") if "applicability" in data else None
    metadata = current_metadata
    metadata.update(_metadata(data.get("metadata")))
    for key in ("description", "notes", "page_reference"):
        if key in data:
            value = _text(data.get(key))
            if value is None:
                metadata.pop(key, None)
            else:
                metadata[key] = value
    metadata.setdefault("lifecycle_status", "ACTIVE")
    metadata["material_type"] = knowledge_type
    metadata["review_status"] = status
    metadata["provenance_type"] = data.get("provenance_type") or metadata.get("provenance_type") or _provenance(source_type, knowledge_type)
    payload: dict[str, Any] = {
        "title": title,
        "knowledge_type": KNOWLEDGE_TYPE_TO_DB[knowledge_type],
        "summary": _text(data.get("summary") or data.get("description")) if ("summary" in data or "description" in data) else current.get("summary"),
        "problem_class": _text(data.get("problem_class")) if "problem_class" in data else current.get("problem_class"),
        "component": _text(data.get("component")) if "component" in data else current.get("component"),
        "symptoms": data.get("symptoms", current.get("symptoms", [])),
        "conditions": data.get("conditions", current.get("conditions", {})),
        "causes": data.get("causes", current.get("causes", [])),
        "checks": data.get("checks", current.get("checks", [])),
        "solutions": data.get("solutions", current.get("solutions", [])),
        "confidence": data.get("confidence", current.get("confidence", 0)),
        "validation_status": REVIEW_STATUS_TO_DB[status],
        "metadata": metadata,
        "updated_at": _now(),
    }
    if applicability is not None:
        configuration = find_or_create_configuration(applicability)
        payload["vehicle_configuration_id"] = configuration.get("id") if configuration else None
    elif not existing:
        payload["vehicle_configuration_id"] = None
    source = None
    if _text(data.get("url")):
        source = {
            "url": data["url"], "title": data.get("source_title") or title,
            "description": data.get("description"), "source_type": source_type or "WEBSITE",
            "metadata": {"page_reference": _text(data.get("page_reference"))},
        }
    return payload, source


def _link_source(knowledge_item_id: Any, source: dict[str, Any] | None, summary: str | None) -> None:
    if not source:
        return
    saved = upsert_source(source)
    if not saved:
        raise HTTPException(status_code=503, detail="Source could not be saved.")
    client = get_supabase_client()
    existing = _one(_execute(
        client.table("knowledge_sources").select("id").eq("knowledge_item_id", knowledge_item_id).eq("source_id", saved["id"]).limit(1),
        "Failed to inspect knowledge source relation.",
    ))
    link = {
        "knowledge_item_id": knowledge_item_id,
        "source_id": saved["id"],
        "relation_type": "SUPPORTS",
        "excerpt": summary,
        "locator": source.get("metadata", {}).get("page_reference"),
        "relevance_score": 1.0,
        "metadata": {"role": "PRIMARY"},
    }
    if existing:
        _execute(client.table("knowledge_sources").update(link).eq("id", existing["id"]), "Failed to update source relation.")
    else:
        _execute(client.table("knowledge_sources").insert(link), "Failed to link knowledge source.")


def create_material(data: dict[str, Any]) -> dict[str, Any]:
    payload, source = build_material_payload(data)
    payload["created_at"] = _now()
    item = _one(_execute(get_supabase_client().table("knowledge_items").insert(payload), "Failed to create knowledge material."))
    if not item:
        raise HTTPException(status_code=503, detail="Knowledge insert returned no row.")
    _link_source(item["id"], source, payload.get("summary"))
    return get_material(str(item["id"]))


def _get_row(table: str, row_id: str, message: str) -> dict[str, Any]:
    item = _one(_execute(get_supabase_client().table(table).select("*").eq("id", row_id).limit(1), message))
    if not item:
        raise HTTPException(status_code=404, detail=f"{table} row not found.")
    return item


def update_material(item_id: str, data: dict[str, Any]) -> dict[str, Any]:
    existing = _get_row("knowledge_items", item_id, "Failed to load knowledge material.")
    payload, source = build_material_payload(data, existing=existing)
    item = _one(_execute(get_supabase_client().table("knowledge_items").update(payload).eq("id", item_id), "Failed to update knowledge material."))
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge material not found.")
    _link_source(item_id, source, payload.get("summary"))
    return get_material(item_id)


def archive_material(item_id: str) -> dict[str, Any]:
    existing = _get_row("knowledge_items", item_id, "Failed to load knowledge material.")
    metadata = _metadata(existing.get("metadata"))
    metadata.update({"lifecycle_status": "ARCHIVED", "archived_at": _now()})
    item = _one(_execute(
        get_supabase_client().table("knowledge_items").update({"metadata": metadata, "updated_at": _now()}).eq("id", item_id),
        "Failed to archive knowledge material.",
    ))
    return item or existing


def _configuration_ids(filters: dict[str, Any]) -> tuple[list[Any], list[dict[str, Any]]]:
    query = get_supabase_client().table("vehicle_configurations").select("*")
    for field in ("make", "model", "generation", "body_type", "engine_code", "transmission", "drivetrain", "market"):
        value = filters.get(field)
        if value not in (None, ""):
            query = query.ilike(field, str(value)) if field in ("make", "model") else query.eq(field, value)
    year = filters.get("year")
    if year not in (None, ""):
        year = int(year)
        query = query.or_(f"year_from.is.null,year_from.lte.{year}").or_(f"year_to.is.null,year_to.gte.{year}")
    configs = rows(_execute(query.limit(5000), "Failed to resolve knowledge applicability."))
    return [item.get("id") for item in configs if item.get("id") is not None], configs


def catalog(*, letter: str | None = None, search: str | None = None) -> dict[str, Any]:
    found: dict[tuple[str, str], dict[str, Any]] = {}
    client = get_supabase_client()
    for table in ("vehicle_configurations", "vehicles"):
        query = client.table(table).select("make,model")
        if search:
            term = str(search).strip().replace(",", " ")
            parts = term.split(None, 1)
            if len(parts) == 2:
                query = query.ilike("make", f"%{parts[0]}%").ilike("model", f"%{parts[1]}%")
            else:
                query = query.or_(f"make.ilike.%{term}%,model.ilike.%{term}%")
        elif letter and letter != "#":
            query = query.ilike("make", f"{letter}%")
        for row in rows(_execute(query.limit(5000), f"Failed to load {table} catalog.")):
            make, model = _text(row.get("make")), _text(row.get("model"))
            if not make or not model:
                continue
            if letter == "#" and make[:1].isalpha():
                continue
            found.setdefault((make.casefold(), model.casefold()), {"make": make, "model": model})
    makes: dict[str, list[str]] = {}
    for item in sorted(found.values(), key=lambda value: (value["make"].casefold(), value["model"].casefold())):
        makes.setdefault(item["make"], []).append(item["model"])
    return {"items": [{"make": make, "models": models} for make, models in makes.items()], "total": len(found)}


def _source_filtered_item_ids(source_type: str | None) -> list[Any] | None:
    if not source_type:
        return None
    sources = rows(_execute(
        get_supabase_client().table("sources").select("id").eq("source_type", source_type).limit(5000),
        "Failed to filter knowledge sources.",
    ))
    source_ids = [row["id"] for row in sources if row.get("id") is not None]
    if not source_ids:
        return []
    links = rows(_execute(
        get_supabase_client().table("knowledge_sources").select("knowledge_item_id").in_("source_id", source_ids).limit(5000),
        "Failed to filter knowledge relations.",
    ))
    return list({row.get("knowledge_item_id") for row in links if row.get("knowledge_item_id") is not None})


def _apply_item_filters(query: Any, filters: dict[str, Any], config_ids: list[Any] | None, source_item_ids: list[Any] | None) -> Any:
    if filters.get("scope") == "general":
        query = query.is_("vehicle_configuration_id", "null")
    elif config_ids is not None:
        if not config_ids:
            return None
        query = query.in_("vehicle_configuration_id", config_ids)
    if source_item_ids is not None:
        if not source_item_ids:
            return None
        query = query.in_("id", source_item_ids)
    if filters.get("knowledge_type"):
        requested = str(filters["knowledge_type"]).upper()
        canonical = KNOWLEDGE_TYPE_TO_DB.get(requested)
        if requested in ("MANUAL", "VIDEO", "OTHER", "FORUM", "SUCCESSFUL_CASE", "MANUFACTURER_DOCUMENT"):
            query = query.eq("knowledge_type", canonical)
        else:
            query = query.eq("metadata->>material_type", requested)
    elif filters.get("category") in CATEGORY_DB_TYPES:
        query = query.in_("knowledge_type", CATEGORY_DB_TYPES[filters["category"]])
    elif filters.get("category") == "specifications":
        query = query.eq("metadata->>material_type", "SPECIFICATION")
    elif filters.get("category") == "procedures":
        query = query.in_("metadata->>material_type", ("PROCEDURE", "DIAGNOSTIC_REFERENCE"))
    if filters.get("validation_status"):
        query = query.eq("validation_status", REVIEW_STATUS_TO_DB.get(str(filters["validation_status"]).upper(), filters["validation_status"]))
    if filters.get("q"):
        term = str(filters["q"]).strip().replace(",", " ")
        query = query.or_(f"title.ilike.%{term}%,summary.ilike.%{term}%,component.ilike.%{term}%")
    if not filters.get("include_archived"):
        query = query.is_("metadata->>archived_at", "null")
    return query


def _enrich_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        return []
    client = get_supabase_client()
    config_ids = list({item.get("vehicle_configuration_id") for item in items if item.get("vehicle_configuration_id") is not None})
    configurations = rows(_execute(client.table("vehicle_configurations").select("*").in_("id", config_ids), "Failed to load applicability.")) if config_ids else []
    config_by_id = {str(item.get("id")): item for item in configurations}
    item_ids = [item["id"] for item in items]
    links = rows(_execute(client.table("knowledge_sources").select("*").in_("knowledge_item_id", item_ids).limit(5000), "Failed to load source relations."))
    source_ids = list({link.get("source_id") for link in links if link.get("source_id") is not None})
    sources = rows(_execute(client.table("sources").select("*").in_("id", source_ids).limit(5000), "Failed to load sources.")) if source_ids else []
    source_by_id = {str(item.get("id")): item for item in sources}
    links_by_item: dict[str, list[dict[str, Any]]] = {}
    for link in links:
        joined = dict(link)
        joined["source"] = source_by_id.get(str(link.get("source_id")))
        links_by_item.setdefault(str(link.get("knowledge_item_id")), []).append(joined)
    enriched = []
    for item in items:
        row = dict(item)
        metadata = _metadata(row.get("metadata"))
        canonical_type = str(row.get("knowledge_type") or "OTHER")
        canonical_status = str(row.get("validation_status") or "UNVERIFIED")
        row["canonical_knowledge_type"] = canonical_type
        row["canonical_validation_status"] = canonical_status
        row["knowledge_type"] = metadata.get("material_type") or DB_TYPE_TO_KNOWLEDGE.get(canonical_type, canonical_type)
        row["validation_status"] = metadata.get("review_status") or DB_STATUS_TO_REVIEW.get(canonical_status, canonical_status)
        row["provenance_type"] = metadata.get("provenance_type") or {
            "MANUFACTURER": "MANUFACTURER", "MANUAL": "MANUAL", "FORUM_CASE": "FORUM_COMMUNITY",
            "PULS_CASE": "SUCCESSFUL_USER_CASE",
        }.get(canonical_type, "EXTERNAL_WEB")
        row["applicability"] = config_by_id.get(str(item.get("vehicle_configuration_id")))
        row["knowledge_sources"] = links_by_item.get(str(item.get("id")), [])
        enriched.append(row)
    return enriched


def list_materials(*, limit: int, offset: int, filters: dict[str, Any]) -> dict[str, Any]:
    limit, offset = _page(limit, offset)
    vehicle_filters = {key: filters.get(key) for key in ("make", "model", "generation", "body_type", "engine_code", "transmission", "drivetrain", "market", "year")}
    has_vehicle_filter = any(value not in (None, "") for value in vehicle_filters.values())
    config_ids, _ = _configuration_ids(vehicle_filters) if has_vehicle_filter else (None, [])
    source_item_ids = _source_filtered_item_ids(filters.get("source_type"))
    base = get_supabase_client().table("knowledge_items").select("*", count="exact")
    query = _apply_item_filters(base, filters, config_ids, source_item_ids)
    if query is None:
        return {"items": [], "total": 0, "limit": limit, "offset": offset, "counts": {}}
    response = _execute(query.order("updated_at", desc=True).range(offset, offset + limit - 1), "Failed to load knowledge library.")
    items = rows(response)
    count = getattr(response, "count", None)
    count_query = _apply_item_filters(get_supabase_client().table("knowledge_items").select("knowledge_type,metadata"), filters | {"knowledge_type": None, "category": None}, config_ids, source_item_ids)
    count_rows = rows(_execute(count_query.limit(5000), "Failed to count knowledge categories.")) if count_query is not None else []
    counts = Counter(str(_metadata(item.get("metadata")).get("material_type") or DB_TYPE_TO_KNOWLEDGE.get(item.get("knowledge_type"), item.get("knowledge_type") or "OTHER")) for item in count_rows)
    counts["ALL"] = len(count_rows)
    return {"items": _enrich_items(items), "total": int(count) if count is not None else len(items), "limit": limit, "offset": offset, "counts": dict(counts)}


def get_material(item_id: str) -> dict[str, Any]:
    item = _get_row("knowledge_items", item_id, "Failed to load knowledge material.")
    return _enrich_items([item])[0]


def list_model_problems(*, limit: int, offset: int, filters: dict[str, Any]) -> dict[str, Any]:
    limit, offset = _page(limit, offset)
    vehicle_query = get_supabase_client().table("vehicles").select("*")
    mapping = {"make": "make", "model": "model", "generation": "generation", "body_type": "body_type", "engine_code": "engine_code", "transmission": "transmission"}
    for source, column in mapping.items():
        if filters.get(source):
            vehicle_query = vehicle_query.ilike(column, str(filters[source])) if source in ("make", "model") else vehicle_query.eq(column, filters[source])
    if filters.get("year"):
        vehicle_query = vehicle_query.eq("year", int(filters["year"]))
    vehicles = rows(_execute(vehicle_query.limit(5000), "Failed to resolve model vehicles."))
    vehicle_ids = [row["id"] for row in vehicles if row.get("id") is not None]
    if not vehicle_ids:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}
    query = get_supabase_client().table("problems").select("*", count="exact").in_("vehicle_id", vehicle_ids)
    response = _execute(query.order("updated_at", desc=True).range(offset, offset + limit - 1), "Failed to load model problems.")
    items = rows(response)
    vehicle_by_id = {str(row["id"]): row for row in vehicles}
    for item in items:
        item["vehicle"] = vehicle_by_id.get(str(item.get("vehicle_id")))
    count = getattr(response, "count", None)
    return {"items": items, "total": int(count) if count is not None else len(items), "limit": limit, "offset": offset}


def _enrich_successful_cases(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        return []
    client = get_supabase_client()
    config_ids = list({item.get("vehicle_configuration_id") for item in items if item.get("vehicle_configuration_id") is not None})
    origin_event_ids = list({item.get("origin_event_id") for item in items if item.get("origin_event_id") is not None})
    configs = rows(_execute(client.table("vehicle_configurations").select("*").in_("id", config_ids), "Failed to load candidate applicability.")) if config_ids else []
    origin_events = rows(_execute(client.table("vehicle_events").select("*").in_("id", origin_event_ids), "Failed to load origin vehicle events.")) if origin_event_ids else []
    problem_ids = list({item.get("problem_id") for item in origin_events if item.get("problem_id") is not None})
    problems = rows(_execute(client.table("problems").select("*").in_("id", problem_ids), "Failed to load original cases.")) if problem_ids else []
    relations = rows(_execute(client.table("problem_sources").select("*").in_("problem_id", problem_ids).limit(5000), "Failed to load candidate sources.")) if problem_ids else []
    source_ids = list({item.get("source_id") for item in relations if item.get("source_id") is not None})
    sources = rows(_execute(client.table("sources").select("*").in_("id", source_ids).limit(5000), "Failed to load candidate source details.")) if source_ids else []
    config_by_id = {str(item.get("id")): item for item in configs}
    origin_by_id = {str(item.get("id")): item for item in origin_events}
    problem_by_id = {str(item.get("id")): item for item in problems}
    source_by_id = {str(item.get("id")): item for item in sources}
    relations_by_problem: dict[str, list[dict[str, Any]]] = {}
    for relation in relations:
        joined = dict(relation)
        joined["source"] = source_by_id.get(str(relation.get("source_id")))
        relations_by_problem.setdefault(str(relation.get("problem_id")), []).append(joined)
    enriched = []
    for item in items:
        row = dict(item)
        origin_event = origin_by_id.get(str(item.get("origin_event_id")))
        problem_id = origin_event.get("problem_id") if origin_event else None
        row["applicability"] = config_by_id.get(str(item.get("vehicle_configuration_id")))
        row["origin_event"] = origin_event
        row["original_problem"] = problem_by_id.get(str(problem_id))
        row["related_sources"] = relations_by_problem.get(str(problem_id), [])
        enriched.append(row)
    return enriched


def list_review_queue(*, limit: int, offset: int, status: str | None = None) -> dict[str, Any]:
    limit, offset = _page(limit, offset)
    status = _enum(status, REVIEW_STATUSES, "review_status", "PENDING_REVIEW")
    query = get_supabase_client().table("knowledge_items").select("*", count="exact").eq("validation_status", REVIEW_STATUS_TO_DB[status]).is_("metadata->>archived_at", "null")
    response = _execute(query.order("updated_at", desc=True).range(offset, offset + limit - 1), "Failed to load review queue.")
    items = [{"candidate_type": "KNOWLEDGE", "candidate": item} for item in _enrich_items(rows(response))]
    knowledge_total = int(getattr(response, "count", None) or len(items))
    total = knowledge_total
    if status == "PENDING_REVIEW":
        reviewed = rows(_execute(
            get_supabase_client().table("knowledge_items").select("metadata").not_.is_("metadata->>origin_fleet_event_id", "null").limit(5000),
            "Failed to resolve reviewed successful cases.",
        ))
        reviewed_ids = [str(item.get("metadata", {}).get("origin_fleet_event_id")) for item in reviewed if item.get("metadata", {}).get("origin_fleet_event_id") is not None]
        def fleet_query() -> Any:
            query = (
                get_supabase_client().table("fleet_events").select("*", count="exact")
                .eq("confirmation_status", "CONFIRMED")
                .in_("result", ("HELPED", "PARTIALLY_HELPED"))
                .not_.is_("action", "null")
            )
            return query.not_.in_("id", reviewed_ids) if reviewed_ids else query
        fleet_count_response = _execute(fleet_query().limit(1), "Failed to count successful case candidates.")
        fleet_total = int(getattr(fleet_count_response, "count", None) or len(rows(fleet_count_response)))
        total += fleet_total
        if len(items) < limit and fleet_total:
            fleet_offset = max(0, offset - knowledge_total)
            fleet_response = _execute(
                fleet_query().order("created_at", desc=True).range(fleet_offset, fleet_offset + (limit - len(items)) - 1),
                "Failed to load successful case candidates.",
            )
            fleet = _enrich_successful_cases(rows(fleet_response))
            items.extend({"candidate_type": "SUCCESSFUL_CASE", "candidate": item} for item in fleet)
    return {"items": items, "total": total, "limit": limit, "offset": offset, "status": status}


def review_candidate(candidate_type: str, candidate_id: str, data: dict[str, Any]) -> dict[str, Any]:
    candidate_type = str(candidate_type or "").upper()
    decision = _enum(data.get("decision"), REVIEW_STATUSES, "decision")
    if not decision:
        raise HTTPException(status_code=400, detail="Review decision is required.")
    review = {
        "decision": decision,
        "technical_comment": _text(data.get("technical_comment")),
        "applicability_clarification": _metadata(data.get("applicability_clarification")),
        "normalized_symptoms": data.get("normalized_symptoms") or [],
        "confirmed_cause": _text(data.get("confirmed_cause")),
        "recommended_checks": data.get("recommended_checks") or [],
        "verification_note": _text(data.get("verification_note")),
        "reviewed_at": _now(),
    }
    client = get_supabase_client()
    if candidate_type == "KNOWLEDGE":
        existing = _get_row("knowledge_items", candidate_id, "Failed to load review candidate.")
        metadata = _metadata(existing.get("metadata"))
        history = list(metadata.get("review_history") or [])
        history.append(review)
        metadata.update({"mechanic_review": review, "review_history": history})
        metadata["review_status"] = decision
        payload: dict[str, Any] = {"validation_status": REVIEW_STATUS_TO_DB[decision], "metadata": metadata, "updated_at": _now()}
        if review["normalized_symptoms"]:
            payload["symptoms"] = review["normalized_symptoms"]
        if review["confirmed_cause"]:
            payload["causes"] = [review["confirmed_cause"]]
        item = _one(_execute(client.table("knowledge_items").update(payload).eq("id", candidate_id), "Failed to save mechanic review."))
        return get_material(str((item or existing)["id"]))
    if candidate_type != "SUCCESSFUL_CASE":
        raise HTTPException(status_code=400, detail="Unsupported review candidate type.")
    original = _get_row("fleet_events", candidate_id, "Failed to load successful case candidate.")
    original_symptoms = original.get("symptoms") if isinstance(original.get("symptoms"), list) else []
    title = _text(original_symptoms[0] if original_symptoms else original.get("cause")) or f"Successful case #{candidate_id}"
    origin_event = None
    original_problem = None
    if original.get("origin_event_id"):
        try:
            origin_event = _get_row("vehicle_events", str(original["origin_event_id"]), "Failed to load successful case origin event.")
            if origin_event.get("problem_id"):
                original_problem = _get_row("problems", str(origin_event["problem_id"]), "Failed to load successful case problem.")
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
    payload = {
        "title": title,
        "knowledge_type": "PULS_CASE",
        "vehicle_configuration_id": original.get("vehicle_configuration_id"),
        "problem_class": original.get("problem_class"),
        "component": original.get("component"),
        "symptoms": review["normalized_symptoms"] or original_symptoms,
        "conditions": original.get("conditions") if isinstance(original.get("conditions"), dict) else {},
        "causes": [review["confirmed_cause"] or original.get("cause")] if (review["confirmed_cause"] or original.get("cause")) else [],
        "checks": review["recommended_checks"] or (_metadata(original.get("metadata")).get("checks") or []),
        "solutions": [original.get("action")] if original.get("action") else [],
        "summary": title,
        "confidence": original.get("confidence", 0),
        "validation_status": REVIEW_STATUS_TO_DB[decision],
        "metadata": {
            "lifecycle_status": "ACTIVE", "material_type": "SUCCESSFUL_CASE",
            "review_status": decision, "provenance_type": "SUCCESSFUL_USER_CASE",
            "origin_fleet_event_id": original.get("id"), "original_case": original,
            "original_case_reference": {
                "origin_event_id": original.get("origin_event_id"),
                "problem_id": origin_event.get("problem_id") if origin_event else None,
            },
            "origin_event": origin_event, "original_problem": original_problem,
            "result": original.get("result"), "mechanic_review": review, "review_history": [review],
        },
        "created_at": _now(), "updated_at": _now(),
    }
    existing = _one(_execute(
        client.table("knowledge_items").select("*").eq("metadata->>origin_fleet_event_id", str(candidate_id)).limit(1),
        "Failed to inspect existing successful case review.",
    ))
    if existing:
        previous_metadata = _metadata(existing.get("metadata"))
        previous_history = list(previous_metadata.get("review_history") or [])
        previous_history.append(review)
        payload["metadata"] = {**previous_metadata, "original_case": previous_metadata.get("original_case") or original, "mechanic_review": review, "review_history": previous_history}
        payload.pop("created_at", None)
        item = _one(_execute(client.table("knowledge_items").update(payload).eq("id", existing["id"]), "Failed to update successful case review."))
    else:
        item = _one(_execute(client.table("knowledge_items").insert(payload), "Failed to save successful case review."))
    if not item:
        raise HTTPException(status_code=503, detail="Reviewed case insert returned no row.")
    return get_material(str(item["id"]))
