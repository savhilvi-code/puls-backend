from fastapi import APIRouter, Query

from app.services.request_journal_service import get_conversation_messages, get_user_request_history

router = APIRouter(prefix="/api", tags=["history"])


@router.get("/history")
async def history(email: str = Query(default=""), user_id: int | None = Query(default=None), limit: int = Query(default=50, ge=1, le=100)):
    items = await get_user_request_history(user_id=user_id, email=email, limit=limit)
    return {"items": items}


@router.get("/history/{conversation_id}")
async def history_messages(conversation_id: int, email: str = Query(default=""), user_id: int | None = Query(default=None)):
    items = await get_conversation_messages(conversation_id=conversation_id, user_id=user_id, email=email)
    return {"items": items}
