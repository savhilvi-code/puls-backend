from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

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
)


router = APIRouter(
    prefix="/admin",
    tags=["admin"],
)


class ChangePlanRequest(BaseModel):
    plan: str


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
