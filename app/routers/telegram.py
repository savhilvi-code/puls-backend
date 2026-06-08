from fastapi import APIRouter, Request

from app.routers.chat import handle_message
from app.services.telegram_service import send_telegram_message

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook")
async def telegram_webhook(request: Request) -> dict[str, bool]:
    update = await request.json()
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    from_user = message.get("from") or {}

    payload = {
        "source": "telegram",
        "text": message.get("text", ""),
        "auth_user_id": str(from_user.get("id") or ""),
        "telegram_id": str(from_user.get("id") or ""),
        "chat_id": str(chat.get("id") or ""),
        "email": "",
        "username": from_user.get("username", ""),
        "first_name": from_user.get("first_name", ""),
        "car_info": "",
        "language": "",
    }

    response = await handle_message(payload, source="telegram")
    if payload["chat_id"] and response.answer:
        await send_telegram_message(chat_id=payload["chat_id"], text=response.answer)

    return {"ok": True}

