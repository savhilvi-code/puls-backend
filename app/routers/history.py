from __future__ import annotations

from fastapi import APIRouter, Request

from app.services.auth_service import get_or_create_profile
from app.services.subscription_service import ensure_user_subscription, quota_payload
from app.services import v2_repository as repo

router = APIRouter(prefix="/api", tags=["conversation"])


@router.get("/quota")
async def quota(request: Request) -> dict:
    user = await get_or_create_profile(request=request, require_auth=True)
    subscription = ensure_user_subscription(user_id=user.id)
    return {"quota": quota_payload(subscription)}


@router.get("/conversations/{conversation_id}/messages")
async def conversation_messages(conversation_id: int, request: Request) -> dict:
    user = await get_or_create_profile(request=request, require_auth=True)
    return {"items": repo.recent_conversation_messages(user_id=user.id, conversation_id=conversation_id, limit=100)}


@router.get("/history")
async def history(request: Request) -> dict:
    user = await get_or_create_profile(request=request, require_auth=True)
    return {"items": repo.recent_conversation_messages(user_id=user.id, limit=50)}


@router.get("/history/{conversation_id}")
async def history_messages(conversation_id: int, request: Request) -> dict:
    return await conversation_messages(conversation_id, request)
