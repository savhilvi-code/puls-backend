from fastapi import HTTPException

from app.database.supabase import (
    SupabaseOperationError,
    SupabaseUnavailableError,
    create_user_record,
    decrement_requests_left,
    find_user_by_fields,
    update_car_info,
    update_conversation_history,
)
from app.services.dialog_state_service import history_context_block
from app.schemas.user import UserRecord

DEFAULT_REQUESTS_LEFT = 5


async def get_or_create_user(normalized) -> UserRecord:
    try:
        existing = find_user_by_fields(
            auth_user_id=normalized.auth_user_id,
            telegram_id=normalized.telegram_id,
            email=normalized.email,
        )
    except SupabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SupabaseOperationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if existing is not None:
        return existing

    payload = {
        "auth_user_id": normalized.auth_user_id or None,
        "telegram_id": normalized.telegram_id or None,
        "email": normalized.email or None,
        "name": normalized.username or normalized.first_name or "",
        "language": normalized.language or "en",
        "conversation_history": "",
        "car_info": normalized.car_info or "",
        "requests_left": DEFAULT_REQUESTS_LEFT,
    }

    try:
        return create_user_record(payload)
    except SupabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SupabaseOperationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


async def update_user_after_response(
    user: UserRecord,
    normalized,
    answer: str,
    should_decrease_limit: bool,
    *,
    active_car: str = "",
    symptom: str = "",
    message_type: str = "diagnostic",
    links: list[dict] | None = None,
) -> None:
    try:
        conversation_history = append_history(
            user.conversation_history,
            user_text=normalized.text,
            answer=answer,
            source=normalized.source,
            active_car=active_car or user.car_info or normalized.car_info,
            symptom=symptom,
            message_type=message_type,
            links=links or [],
        )
        updated_user = update_conversation_history(user.id, conversation_history) if user.id is not None else None
        if (active_car or normalized.car_info) and user.id is not None:
            updated_user = update_car_info(user.id, active_car or normalized.car_info) or updated_user
        if should_decrease_limit and user.id is not None:
            updated_user = decrement_requests_left(user.id) or updated_user
        if updated_user is not None:
            user.conversation_history = updated_user.conversation_history
            user.car_info = updated_user.car_info
            user.requests_left = updated_user.requests_left
    except SupabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SupabaseOperationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def append_history(
    current: str,
    *,
    user_text: str,
    answer: str,
    source: str,
    active_car: str,
    symptom: str,
    message_type: str,
    links: list[dict],
) -> str:
    entry = history_context_block(
        source=source,
        message_type=message_type,
        active_car=active_car,
        symptom=symptom,
        user_text=user_text,
        assistant_text=answer,
        links=links,
    )
    if current and current.strip():
        return current.rstrip() + "\n" + entry
    return entry
