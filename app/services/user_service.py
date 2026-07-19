from __future__ import annotations

import logging

from app.database.supabase import (
    SupabaseOperationError,
    SupabaseUnavailableError,
    create_user_record,
    find_user_by_fields,
)
from app.schemas.user import UserRecord
from app.services.conversation_service import (
    build_user_conversation_history,
    get_latest_active_car,
    get_or_create_conversation,
    save_message,
)
from app.services.diagnostic_service import (
    create_diagnostic_request,
    get_latest_diagnostic_request,
    update_diagnostic_request,
)
from app.services.feedback_service import create_feedback
from app.services.link_service import extract_videos
from app.services.media_service import save_media_files
from app.services.parser_run_service import create_parser_run
from app.services.puls_data_service import (
    classify_feedback,
    create_solved_case,
    create_solved_case_from_diagnostic,
)
from app.services.kb_service import save_confirmed_case_to_knowledge
from app.services.subscription_service import (
    FREE_LIMIT,
    consume_parser_credit,
    ensure_user_subscription,
)

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
        requests_left=FREE_LIMIT,
    )


def _hydrate_runtime_fields(user: UserRecord) -> UserRecord:
    subscription = ensure_user_subscription(user_id=user.id)
    user.requests_left = int((subscription or {}).get("remaining") or FREE_LIMIT)
    user.car_info = get_latest_active_car(user_id=user.id)
    user.conversation_history = build_user_conversation_history(user_id=user.id)
    return user


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
        return _hydrate_runtime_fields(existing)

    payload = {
        "auth_user_id": normalized.auth_user_id or None,
        "email": normalized.email or None,
        "name": normalized.username or normalized.first_name or "",
        "language": normalized.language or "en",
        "source": "web",
    }

    try:
        created = create_user_record(payload)
        ensure_user_subscription(user_id=created.id)
        return _hydrate_runtime_fields(created)
    except SupabaseUnavailableError as exc:
        logger.warning("Using transient user because Supabase is unavailable: %s", exc)
        return _build_transient_user(normalized)
    except SupabaseOperationError as exc:
        logger.exception("Using transient user because Supabase user creation failed: %s", exc)
        return _build_transient_user(normalized)


def _status_for_message_type(message_type: str) -> str:
    message_type = str(message_type or "").strip().lower()
    if message_type in {"feedback_helped", "resolved"}:
        return "solved"
    if message_type in {"feedback_not_helped", "followup_deep"}:
        return "need_deep_search"
    if message_type in {"parser", "parser_fallback", "kb_match"}:
        return "answered"
    if message_type == "clarification":
        return "clarifying"
    return "new"


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
    force_new_conversation: bool = False,
) -> None:
    try:
        conversation = get_or_create_conversation(
            user_id=user.id,
            vehicle_id=vehicle_id,
            title=symptom or normalized.text,
            force_new_context=force_new_conversation,
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

        normalized_links = links or []
        feedback_type = classify_feedback(message_type, normalized.text)
        diagnostic_request = None
        diagnostic_request_id = None
        request_type = "text"

        if parser_used:
            request_type = "deep_search" if deep_search_used else "parser"
        elif message_type == "kb_match":
            request_type = "kb"

        should_create_diagnostic = (
            user.id is not None
            and (parser_used or deep_search_used or message_type == "kb_match")
        )

        if should_create_diagnostic:
            diagnostic_request = create_diagnostic_request(
                user_id=user.id,
                conversation_id=conversation_id,
                vehicle_id=vehicle_id,
                question=(symptom or normalized.text or "").strip(),
                answer=answer,
                language=normalized.language,
                request_type=request_type,
                status=_status_for_message_type(message_type),
                parser_used=parser_used,
                deep_search_used=deep_search_used,
                request_cost_counted=False,
                sources=normalized_links,
                videos=extract_videos(normalized_links),
            )
            diagnostic_request_id = diagnostic_request.get("id") if diagnostic_request else None

            if parsed_case and (parser_used or deep_search_used):
                parser_run = create_parser_run(
                    user_id=user.id,
                    vehicle_id=vehicle_id,
                    conversation_id=conversation_id,
                    diagnostic_request_id=diagnostic_request_id,
                    run_type="deep_search" if deep_search_used else "parser",
                    query_original=symptom or normalized.text,
                    parsed_case=parsed_case,
                )
                if parser_run and should_decrease_limit:
                    consume_parser_credit(user_id=user.id)
                    update_diagnostic_request(
                        diagnostic_request_id=diagnostic_request_id,
                        payload={"request_cost_counted": True},
                    )

            save_media_files(
                user_id=user.id,
                vehicle_id=vehicle_id,
                diagnostic_request_id=diagnostic_request_id,
                links=normalized_links,
            )

        if user.id is not None and feedback_type:
            latest_diagnostic = get_latest_diagnostic_request(
                user_id=user.id,
                conversation_id=conversation_id,
            )
            target_request = diagnostic_request or latest_diagnostic
            target_request_id = (target_request or {}).get("id")
            create_feedback(
                user_id=user.id,
                vehicle_id=vehicle_id if vehicle_id is not None else (target_request or {}).get("vehicle_id"),
                conversation_id=conversation_id,
                diagnostic_request_id=target_request_id,
                feedback_type=feedback_type,
                feedback_text=normalized.text,
            )
            if feedback_type == "helped" and target_request:
                update_diagnostic_request(
                    diagnostic_request_id=target_request_id,
                    payload={"status": "solved"},
                )
                create_solved_case_from_diagnostic(
                    user_id=user.id,
                    vehicle_id=vehicle_id,
                    diagnostic_request=target_request,
                    car_info=active_car or normalized.car_info,
                )
                await save_confirmed_case_to_knowledge(
                    diagnostic_request=target_request,
                    active_car=active_car or normalized.car_info,
                    language=normalized.language,
                )
            elif feedback_type in {"not_helped", "need_more", "unclear"} and target_request_id:
                update_diagnostic_request(
                    diagnostic_request_id=target_request_id,
                    payload={"status": "need_deep_search"},
                )

        _hydrate_runtime_fields(user)
    except SupabaseUnavailableError as exc:
        logger.warning("Skipped persistence because Supabase is unavailable: %s", exc)
    except SupabaseOperationError as exc:
        logger.exception("Skipped persistence because Supabase update failed: %s", exc)
    except Exception as exc:
        logger.exception("Unexpected persistence failure: %s", exc)
