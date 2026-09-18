from fastapi import APIRouter, Request

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.decision_engine import process_chat_message
from app.services.trace_service import current_trace_id, finish_trace, start_trace

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    token = start_trace(message=payload.text, source="web")
    trace_id = current_trace_id()
    try:
        response = await process_chat_message(payload.model_dump(), source="web", request=request)
        response.trace_id = trace_id
        finish_trace(status="COMPLETED", response={"conversation_id": response.conversation_id, "answer_excerpt": response.answer[:240]}, token=token)
        return response
    except Exception as exc:
        finish_trace(status="FAILED", error_code=type(exc).__name__, token=token)
        raise
