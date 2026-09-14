from fastapi import APIRouter, Query

from app.database.supabase import find_user_by_fields, get_user_by_id
from app.services.request_journal_service import get_conversation_messages, get_user_request_history
from app.services.subscription_service import ensure_user_subscription, quota_payload

router = APIRouter(prefix="/api", tags=["history"])


@router.get("/quota")
async def quota(
    email: str = Query(default=""),
    user_id: int | None = Query(default=None),
    auth_user_id: str = Query(default=""),
):
    user = get_user_by_id(user_id) if user_id is not None else find_user_by_fields(auth_user_id=auth_user_id, email=email)
    subscription = ensure_user_subscription(user_id=user.id if user else None)
    return {"quota": quota_payload(subscription)}


@router.get("/history")
async def history(email: str = Query(default=""), user_id: int | None = Query(default=None), limit: int = Query(default=50, ge=1, le=100)):
    items = await get_user_request_history(user_id=user_id, email=email, limit=limit)
    return {"items": items}


@router.get("/history/{conversation_id}")
async def history_messages(conversation_id: int, email: str = Query(default=""), user_id: int | None = Query(default=None)):
    items = await get_conversation_messages(conversation_id=conversation_id, user_id=user_id, email=email)
    return {"items": items}
