from fastapi import APIRouter

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.decision_engine import process_chat_message

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    return await process_chat_message(payload.model_dump(), source="web")
