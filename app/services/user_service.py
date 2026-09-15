from __future__ import annotations

from typing import Any

from app.schemas.user import UserRecord
from app.services.auth_service import get_or_create_profile, transient_user
from app.services.subscription_service import ensure_user_subscription
from app.services import v2_repository as repo


async def get_or_create_user(normalized) -> UserRecord:
    payload = normalized.model_dump() if hasattr(normalized, "model_dump") else vars(normalized)
    return await get_or_create_profile(payload=payload, require_auth=False)


async def update_user_after_response(
    user: UserRecord,
    normalized,
    answer: str,
    should_decrease_limit: bool,
    *,
    vehicle_id: str | None = None,
    problem_id: str | None = None,
    message_type: str = "general",
    **_: Any,
) -> None:
    if user.id is None:
        return
    conversation = repo.get_or_create_conversation(
        user_id=user.id,
        vehicle_id=vehicle_id,
        problem_id=problem_id,
        title=getattr(normalized, "text", "") or "",
    )
    conversation_id = (conversation or {}).get("id")
    repo.save_message(
        user_id=user.id,
        conversation_id=conversation_id,
        vehicle_id=vehicle_id,
        problem_id=problem_id,
        role="user",
        text=getattr(normalized, "text", "") or "",
        language=getattr(normalized, "language", "en") or "en",
    )
    repo.save_message(
        user_id=user.id,
        conversation_id=conversation_id,
        vehicle_id=vehicle_id,
        problem_id=problem_id,
        role="assistant",
        text=answer,
        language=getattr(normalized, "language", "en") or "en",
    )
    if should_decrease_limit:
        from app.services.subscription_service import consume_research_credit

        consume_research_credit(user_id=user.id)
    ensure_user_subscription(user_id=user.id)


__all__ = ["get_or_create_user", "update_user_after_response", "transient_user"]
