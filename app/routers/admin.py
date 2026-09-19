from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.admin_service import (
    block_user,
    change_user_plan,
    clear_user_history,
    delete_user_permanently,
    get_admin_user,
    list_users,
    require_admin,
    reset_user_quota,
    unblock_user,
)
from app.services.admin_inspector_service import (
    get_overview,
    get_problem_trace,
    list_conversation_messages,
    list_conversations,
    list_fleet_events,
    list_knowledge_items,
    list_problems,
    list_search_episodes,
    list_search_runs,
    list_sources,
    list_vehicle_events,
    list_vehicle_specs,
    list_vehicles,
)
from app.services.trace_service import event_stream, get_trace, list_traces
from app.services.knowledge_library_service import (
    archive_material,
    catalog as knowledge_catalog,
    create_material,
    get_material,
    list_materials,
    list_model_problems,
    list_review_queue,
    review_candidate,
    update_material,
)
from app.services.admin_delete_service import (
    delete_knowledge_material,
    delete_successful_case,
    delete_vehicle as hard_delete_vehicle,
    preview_knowledge_delete,
    preview_successful_case_delete,
    preview_vehicle_delete,
)


router = APIRouter(
    prefix="/admin",
    tags=["admin"],
)


class ChangePlanRequest(BaseModel):
    plan: str


class KnowledgeMaterialRequest(BaseModel):
    title: str
    knowledge_type: str = "OTHER"
    description: str | None = None
    summary: str | None = None
    url: str | None = None
    source_title: str | None = None
    source_type: str | None = None
    page_reference: str | None = None
    validation_status: str = "PENDING_REVIEW"
    problem_class: str | None = None
    component: str | None = None
    symptoms: list[Any] = Field(default_factory=list)
    conditions: dict[str, Any] = Field(default_factory=dict)
    causes: list[Any] = Field(default_factory=list)
    checks: list[Any] = Field(default_factory=list)
    solutions: list[Any] = Field(default_factory=list)
    confidence: float = 0
    notes: str | None = None
    applicability: dict[str, Any] | None = None


class KnowledgeMaterialUpdateRequest(BaseModel):
    title: str | None = None
    knowledge_type: str | None = None
    description: str | None = None
    summary: str | None = None
    url: str | None = None
    source_title: str | None = None
    source_type: str | None = None
    page_reference: str | None = None
    validation_status: str | None = None
    problem_class: str | None = None
    component: str | None = None
    symptoms: list[Any] | None = None
    conditions: dict[str, Any] | None = None
    causes: list[Any] | None = None
    checks: list[Any] | None = None
    solutions: list[Any] | None = None
    confidence: float | None = None
    notes: str | None = None
    applicability: dict[str, Any] | None = None


class KnowledgeReviewRequest(BaseModel):
    candidate_type: str
    candidate_id: str
    decision: str
    applicability_clarification: dict[str, Any] = Field(default_factory=dict)
    technical_comment: str | None = None
    normalized_symptoms: list[Any] = Field(default_factory=list)
    confirmed_cause: str | None = None
    recommended_checks: list[Any] = Field(default_factory=list)
    verification_note: str | None = None


def _model_payload(payload: BaseModel, *, exclude_unset: bool = False) -> dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_unset=exclude_unset)
    return payload.dict(exclude_unset=exclude_unset)


@router.get("/knowledge/library/catalog")
async def admin_knowledge_catalog(
    request: Request, letter: str | None = None, q: str | None = None,
) -> dict[str, Any]:
    require_admin(request)
    return knowledge_catalog(letter=letter, search=q)


@router.get("/knowledge/library/items")
async def admin_knowledge_library_items(
    request: Request, limit: int = 25, offset: int = 0,
    scope: str | None = None, make: str | None = None, model: str | None = None,
    knowledge_type: str | None = None, source_type: str | None = None,
    review_status: str | None = None, engine: str | None = None,
    transmission: str | None = None, year: int | None = None,
    generation: str | None = None, body: str | None = None,
    drivetrain: str | None = None, market: str | None = None,
    q: str | None = None, category: str | None = None, include_archived: bool = False,
) -> dict[str, Any]:
    require_admin(request)
    return list_materials(limit=limit, offset=offset, filters={
        "scope": scope, "make": make, "model": model, "knowledge_type": knowledge_type,
        "source_type": source_type, "validation_status": review_status,
        "category": category,
        "engine_code": engine, "transmission": transmission, "year": year,
        "generation": generation, "body_type": body, "drivetrain": drivetrain,
        "market": market, "q": q, "include_archived": include_archived,
    })


@router.get("/knowledge/library/items/{item_id}")
async def admin_knowledge_library_item(item_id: str, request: Request) -> dict[str, Any]:
    require_admin(request)
    return get_material(item_id)


@router.post("/knowledge/library/items")
async def admin_create_knowledge_material(payload: KnowledgeMaterialRequest, request: Request) -> dict[str, Any]:
    require_admin(request)
    return create_material(_model_payload(payload))


@router.patch("/knowledge/library/items/{item_id}")
async def admin_update_knowledge_material(item_id: str, payload: KnowledgeMaterialUpdateRequest, request: Request) -> dict[str, Any]:
    require_admin(request)
    return update_material(item_id, _model_payload(payload, exclude_unset=True))


@router.post("/knowledge/library/items/{item_id}/archive")
async def admin_archive_knowledge_material(item_id: str, request: Request) -> dict[str, Any]:
    require_admin(request)
    return archive_material(item_id)


@router.get("/knowledge/library/items/{item_id}/delete-preview")
async def admin_preview_knowledge_material_delete(item_id: str, request: Request) -> dict[str, Any]:
    require_admin(request)
    return preview_knowledge_delete(item_id)


@router.delete("/knowledge/library/items/{item_id}")
async def admin_delete_knowledge_material(item_id: str, request: Request) -> dict[str, Any]:
    require_admin(request)
    return delete_knowledge_material(item_id)


@router.get("/knowledge/library/successful-cases/{case_id}/delete-preview")
async def admin_preview_successful_case_delete(case_id: str, request: Request) -> dict[str, Any]:
    require_admin(request)
    return preview_successful_case_delete(case_id)


@router.delete("/knowledge/library/successful-cases/{case_id}")
async def admin_delete_successful_case(case_id: str, request: Request) -> dict[str, Any]:
    require_admin(request)
    return delete_successful_case(case_id)


@router.get("/knowledge/library/vehicles/{vehicle_id}/delete-preview")
async def admin_preview_vehicle_delete(vehicle_id: str, request: Request) -> dict[str, Any]:
    require_admin(request)
    return preview_vehicle_delete(vehicle_id)


@router.delete("/knowledge/library/vehicles/{vehicle_id}")
async def admin_delete_vehicle(vehicle_id: str, request: Request) -> dict[str, Any]:
    require_admin(request)
    return hard_delete_vehicle(vehicle_id)


@router.get("/knowledge/library/problems")
async def admin_knowledge_model_problems(
    request: Request, limit: int = 25, offset: int = 0,
    make: str | None = None, model: str | None = None, year: int | None = None,
    generation: str | None = None, body: str | None = None, engine: str | None = None,
    transmission: str | None = None,
) -> dict[str, Any]:
    require_admin(request)
    return list_model_problems(limit=limit, offset=offset, filters={
        "make": make, "model": model, "year": year, "generation": generation,
        "body_type": body, "engine_code": engine, "transmission": transmission,
    })


@router.get("/knowledge/library/review-queue")
async def admin_knowledge_review_queue(
    request: Request, limit: int = 25, offset: int = 0, status: str | None = None,
) -> dict[str, Any]:
    require_admin(request)
    return list_review_queue(limit=limit, offset=offset, status=status)


@router.post("/knowledge/library/reviews")
async def admin_review_knowledge_candidate(payload: KnowledgeReviewRequest, request: Request) -> dict[str, Any]:
    require_admin(request)
    data = _model_payload(payload)
    return review_candidate(data.pop("candidate_type"), data.pop("candidate_id"), data)


@router.get("/knowledge/live-flow/traces")
async def admin_live_flow_traces(
    request: Request, limit: int = 50, status: str | None = None,
    user_id: str | None = None, vehicle_id: str | None = None,
    intent: str | None = None,
) -> dict[str, Any]:
    require_admin(request)
    return {"items": list_traces(limit=limit, status=status, user_id=user_id, vehicle_id=vehicle_id, intent=intent)}


@router.get("/knowledge/live-flow/traces/{trace_id}")
async def admin_live_flow_trace(trace_id: str, request: Request) -> dict[str, Any]:
    require_admin(request)
    trace = get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found.")
    return trace


@router.get("/knowledge/live-flow/stream")
async def admin_live_flow_stream(
    request: Request, trace_id: str, after_sequence: int = 0,
) -> StreamingResponse:
    require_admin(request)
    return StreamingResponse(
        event_stream(trace_id, request, after_sequence),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/knowledge/overview")
async def admin_knowledge_overview(request: Request) -> dict[str, Any]:
    require_admin(request)
    return get_overview()


@router.get("/knowledge/conversations")
async def admin_knowledge_conversations(
    request: Request, limit: int = 25, offset: int = 0,
    status: str | None = None, q: str | None = None,
) -> dict[str, Any]:
    require_admin(request)
    return list_conversations(limit=limit, offset=offset, status=status, search=q)


@router.get("/knowledge/conversations/{conversation_id}/messages")
async def admin_knowledge_conversation_messages(
    conversation_id: str, request: Request, limit: int = 100, offset: int = 0,
) -> dict[str, Any]:
    require_admin(request)
    return list_conversation_messages(conversation_id, limit=limit, offset=offset)


@router.get("/knowledge/vehicles")
async def admin_knowledge_vehicles(
    request: Request, limit: int = 25, offset: int = 0,
    lifecycle_status: str | None = None, q: str | None = None,
) -> dict[str, Any]:
    require_admin(request)
    return list_vehicles(
        limit=limit, offset=offset, lifecycle_status=lifecycle_status, search=q,
    )


@router.get("/knowledge/vehicles/{vehicle_id}/specs")
async def admin_knowledge_vehicle_specs(
    vehicle_id: str, request: Request, limit: int = 100, offset: int = 0,
) -> dict[str, Any]:
    require_admin(request)
    return list_vehicle_specs(vehicle_id, limit=limit, offset=offset)


@router.get("/knowledge/problems")
async def admin_knowledge_problems(
    request: Request, limit: int = 25, offset: int = 0,
    status: str | None = None, problem_class: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    require_admin(request)
    return list_problems(
        limit=limit, offset=offset, status=status,
        problem_class=problem_class, search=q,
    )


@router.get("/knowledge/problems/{problem_id}/trace")
async def admin_knowledge_problem_trace(problem_id: str, request: Request) -> dict[str, Any]:
    require_admin(request)
    return get_problem_trace(problem_id)


@router.get("/knowledge/vehicle-events")
async def admin_knowledge_vehicle_events(
    request: Request, limit: int = 25, offset: int = 0,
    event_type: str | None = None, q: str | None = None,
) -> dict[str, Any]:
    require_admin(request)
    return list_vehicle_events(
        limit=limit, offset=offset, event_type=event_type, search=q,
    )


@router.get("/knowledge/search-episodes")
async def admin_knowledge_search_episodes(
    request: Request, limit: int = 25, offset: int = 0,
    status: str | None = None,
) -> dict[str, Any]:
    require_admin(request)
    return list_search_episodes(limit=limit, offset=offset, status=status)


@router.get("/knowledge/search-episodes/{episode_id}/runs")
async def admin_knowledge_search_runs(
    episode_id: str, request: Request, limit: int = 50, offset: int = 0,
) -> dict[str, Any]:
    require_admin(request)
    return list_search_runs(episode_id, limit=limit, offset=offset)


@router.get("/knowledge/sources")
async def admin_knowledge_sources(
    request: Request, limit: int = 25, offset: int = 0,
    source_type: str | None = None, q: str | None = None,
) -> dict[str, Any]:
    require_admin(request)
    return list_sources(
        limit=limit, offset=offset, source_type=source_type, search=q,
    )


@router.get("/knowledge/items")
async def admin_knowledge_items(
    request: Request, limit: int = 25, offset: int = 0, q: str | None = None,
) -> dict[str, Any]:
    require_admin(request)
    return list_knowledge_items(limit=limit, offset=offset, search=q)


@router.get("/knowledge/fleet-events")
async def admin_knowledge_fleet_events(
    request: Request, limit: int = 25, offset: int = 0, q: str | None = None,
) -> dict[str, Any]:
    require_admin(request)
    return list_fleet_events(limit=limit, offset=offset, search=q)


@router.get("/users")
async def admin_list_users(
    request: Request,
) -> dict[str, Any]:

    require_admin(request)

    users = list_users()

    return {
        "users": users,
        "count": len(users),
    }


@router.get("/users/{user_id}")
async def admin_get_user(
    user_id: str,
    request: Request,
) -> dict[str, Any]:

    require_admin(request)

    return {
        "user": get_admin_user(user_id),
    }


@router.post("/users/{user_id}/reset-quota")
async def admin_reset_quota(
    user_id: str,
    request: Request,
) -> dict[str, Any]:

    require_admin(request)

    return {
        "success": True,
        "subscription": reset_user_quota(user_id),
    }


@router.patch("/users/{user_id}/plan")
async def admin_change_plan(
    user_id: str,
    payload: ChangePlanRequest,
    request: Request,
) -> dict[str, Any]:

    require_admin(request)

    return {
        "success": True,
        "subscription": change_user_plan(
            user_id,
            payload.plan,
        ),
    }


@router.post("/users/{user_id}/block")
async def admin_block_user(
    user_id: str,
    request: Request,
) -> dict[str, Any]:

    acting_admin_id = require_admin(request)

    if user_id == acting_admin_id:
        raise HTTPException(
            status_code=400,
            detail="Administrator cannot block their own account.",
        )

    return {
        "success": True,
        "user": block_user(user_id),
    }


@router.post("/users/{user_id}/unblock")
async def admin_unblock_user(
    user_id: str,
    request: Request,
) -> dict[str, Any]:

    require_admin(request)

    return {
        "success": True,
        "user": unblock_user(user_id),
    }


@router.post("/users/{user_id}/clear-history")
async def admin_clear_user_history(
    user_id: str,
    request: Request,
) -> dict[str, Any]:
    """
    Delete the user's conversations and diagnostic history
    while preserving the account, subscription and vehicles.
    """

    require_admin(request)

    cleared = clear_user_history(user_id)

    return {
        "success": True,
        "history": cleared,
    }


@router.delete("/users/{user_id}")
async def admin_delete_user(
    user_id: str,
    request: Request,
) -> dict[str, Any]:

    acting_admin_id = require_admin(request)

    deleted = delete_user_permanently(
        user_id,
        acting_admin_id=acting_admin_id,
    )

    return {
        "success": True,
        "user": deleted,
    }
