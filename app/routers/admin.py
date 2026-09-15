from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.services.admin_service import (
    block_user,
    change_user_plan,
    delete_user_permanently,
    get_admin_user,
    list_users,
    require_admin,
    reset_user_quota,
    unblock_user,
)


router = APIRouter(
    prefix="/admin",
    tags=["admin"],
)


class ChangePlanRequest(BaseModel):
    plan: str


@router.get("/users")
async def admin_list_users(request: Request) -> dict[str, Any]:
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
        return {
            "success": False,
            "detail": "Administrator cannot block their own account.",
        }

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
