import logging

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
from app.services.puls_data_service import (
    classify_feedback,
    create_solved_case,
    create_solved_case_from_diagnostic,
    get_latest_answered_diagnostic_request,
    get_active_conversation,
    save_diagnostic_event,
    save_feedback,
    save_message,
    save_parser_run,
    save_video_library,
)
from app.schemas.user import UserRecord

DEFAULT_REQUESTS_LEFT = 10
logger = logging.getLogger(__name__)


def _build_transient_user(normalized) -> UserRecord:
    return UserRecord(
        id=None,
        auth_user_id=normalized.auth_user_id or "",
        email=normalized.email or "",
        username=normalized.username or normalized.first_name or "",
        first_name=normalized.first_name or "",
        car_info=normalized.car_info or "",
        language=normalized.language or "en",
        conversation_history="",
        requests_left=DEFAULT_REQUESTS_LEFT,
    )


async def get_or_create_user(normalized) -> UserRecord:
    try:
        existing = find_user_by_fields(
            auth_user_id=normalized.auth_user_id,
            email=normalized.email,
        )
    except SupabaseUnavailableError as exc:
        logger.warning("Using transient user because Supabase is unavailable: %s", exc)
        return _build_transient_user(normalized)
    except SupabaseOperationError as exc:
        logger.exception("Using transient user because Supabase lookup failed: %s", exc)
        return _build_transient_user(normalized)

    if existing is not None:
        return existing

    payload = {
        "auth_user_id": normalized.auth_user_id or None,
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
        logger.warning("Using transient user because Supabase is unavailable: %s", exc)
        return _build_transient_user(normalized)
    except SupabaseOperationError as exc:
        logger.exception("Using transient user because Supabase user creation failed: %s", exc)
        return _build_transient_user(normalized)


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
    parser_used: bool = False,
    deep_search_used: bool = False,
    vehicle_id: int | None = None,
    vehicle_profile_id: int | None = None,
    parsed_case: dict | None = None,
) -> None:
    try:
        conversation = get_active_conversation(
            user_id=user.id,
            vehicle_id=vehicle_id,
            title=symptom or normalized.text,
        )
        conversation_id = conversation.get("id") if conversation else None
        save_message(
            conversation_id=conversation_id,
            user_id=user.id,
            vehicle_id=vehicle_id,
            role="user",
            text=normalized.text,
            language=normalized.language,
        )
        save_message(
            conversation_id=conversation_id,
            user_id=user.id,
            vehicle_id=vehicle_id,
            role="assistant",
            text=answer,
            language=normalized.language,
        )

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

        diagnostic_request = None
        feedback_type = classify_feedback(message_type, normalized.text)
        is_feedback_only = message_type in {"feedback_helped", "feedback_not_helped"} and not parser_used and not deep_search_used
        diagnostic_request_id = None

        if user.id is not None and message_type not in {"greeting", "limit"} and not is_feedback_only:
            diagnostic_question = (symptom or normalized.text or "").strip()
            diagnostic_request = save_diagnostic_event(
                user_id=user.id,
                conversation_id=conversation_id,
                vehicle_id=vehicle_id,
                vehicle_profile_id=vehicle_profile_id,
                question=diagnostic_question,
                answer=answer,
                language=normalized.language,
                status=_status_for_message_type(message_type),
                message_type=message_type,
                parser_used=parser_used,
                deep_search_used=deep_search_used,
                cost_counted=should_decrease_limit,
                links=links or [],
            )
            diagnostic_request_id = diagnostic_request.get("id") if diagnostic_request else None
            if parsed_case and (parser_used or deep_search_used):
                save_parser_run(
                    user_id=user.id,
                    conversation_id=conversation_id,
                    vehicle_id=vehicle_id,
                    diagnostic_request_id=diagnostic_request_id,
                    run_type="deep_search" if deep_search_used else "parser",
                    query=symptom or normalized.text,
                    parsed_case=parsed_case,
                )
            save_video_library(
                user_id=user.id,
                vehicle_id=vehicle_id,
                diagnostic_request_id=diagnostic_request_id,
                links=links or [],
                topic=symptom or normalized.text,
            )
        if user.id is not None and feedback_type:
            latest_diagnostic = get_latest_answered_diagnostic_request(
                user_id=user.id,
                conversation_id=conversation_id,
                exclude_id=diagnostic_request_id,
            )
            target_diagnostic_id = diagnostic_request_id or ((latest_diagnostic or {}).get("id"))
            save_feedback(
                user_id=user.id,
                vehicle_id=vehicle_id or ((latest_diagnostic or {}).get("vehicle_id")),
                conversation_id=conversation_id,
                diagnostic_request_id=target_diagnostic_id,
                feedback_type=feedback_type,
                feedback_text=normalized.text,
            )
            if feedback_type == "helped":
                created = create_solved_case_from_diagnostic(
                    user_id=user.id,
                    vehicle_id=vehicle_id,
                    diagnostic_request=latest_diagnostic,
                    car_info=active_car or user.car_info or normalized.car_info,
                )
                if created is None and not is_feedback_only:
                    create_solved_case(
                        user_id=user.id,
                        vehicle_id=vehicle_id,
                        diagnostic_request_id=diagnostic_request_id,
                        car_info=active_car or user.car_info or normalized.car_info,
                        symptoms=symptom,
                        confirmed_problem=symptom,
                        confirmed_solution=answer,
                        links=links or [],
                    )
    except SupabaseUnavailableError as exc:
        logger.warning("Skipped persistence because Supabase is unavailable: %s", exc)
        return None
    except SupabaseOperationError as exc:
        logger.exception("Skipped persistence because Supabase update failed: %s", exc)
        return None


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


def _status_for_message_type(message_type: str) -> str:
    message_type = str(message_type or "").strip().lower()
    if message_type in {"feedback_helped", "resolved"}:
        return "resolved"
    if message_type in {"feedback_not_helped", "followup_deep"}:
        return "need_deep_search"
    if message_type in {"parser", "parser_fallback", "kb_match"}:
        return "answered"
    if message_type == "clarification":
        return "new"
    return "new"
