from __future__ import annotations

from typing import Any

from fastapi import Request

from app.schemas.chat import ChatResponse
from app.services.conversation_orchestrator import process_chat_message_v2


async def process_chat_message(payload: dict[str, Any], source: str = "web", request: Request | None = None) -> ChatResponse:
    return await process_chat_message_v2(payload, source=source, request=request)
