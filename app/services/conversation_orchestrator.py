from __future__ import annotations

from datetime import datetime, timezone
import time

from typing import Any
from uuid import UUID

from fastapi import Request

from app.database.supabase import SupabaseOperationError, SupabaseUnavailableError
from app.schemas.chat import ChatResponse
from app.services.auth_service import get_or_create_profile
from app.services.openai_service import (
    OpenAIRouterUnavailableError,
    classify_turn_intent,
    generate_natural_chat_reply,
)
from app.services.search_stage_service import run_search_stages
from app.services.trace_service import bind_trace, emit_event
from app.services.formatter_service import format_technical_answer
from app.services.subscription_service import (
    ensure_user_subscription,
    quota_payload,
)
from app.services.vehicle_fact_service import (
    extract_vehicle_correction,
    extract_vehicle_spec_fact,
    extract_wheel_spec_facts,
    persist_vehicle_correction,
    persist_vehicle_spec_fact,
)
from app.services.v2_context import (
    TurnContext,
    clarification_for,
    classify_problem,
    extract_technical_events,
    extract_vehicle_label,
    has_automotive_content,
    is_factual_technical_statement,
    is_problem_continuation,
    is_social_general_text,
    looks_like_meta_question,
    plain_text_response,
    merge_problem_symptoms,
    normalize_technical_symptom,
    symptom_has_operating_detail,
    vehicle_label,
)
from app.services import v2_repository as repo
from app.utils.language import (
    detect_language,
    normalize_language_code,
    requested_response_language,
)


def _vehicle_match_score(
    vehicle: dict[str, Any],
    car_text: str,
) -> int:
    text = " ".join(
        str(car_text or "").lower().split()
    )

    if not text:
        return 0

    score = 0

    fields = (
        ("make", 4),
        ("model", 4),
        ("generation", 2),
        ("engine_code", 2),
        ("year", 2),
        ("vin", 5),
        ("chassis_number", 5),
    )

    for key, weight in fields:
        value = str(
            vehicle.get(key) or ""
        ).lower().strip()

        if not value:
            continue

        if value in text:
            score += weight
            continue

        parts = value.replace("-", " ").split()

        if any(
            part and part in text
            for part in parts
        ):
            score += 1

    return score


def resolve_relevant_vehicle(
    *,
    vehicles: list[dict[str, Any]],
    explicit_vehicle_id: str | None,
    user_text: str,
    latest_problem: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, bool]:
    if explicit_vehicle_id:
        explicit = next(
            (
                item
                for item in vehicles
                if str(item.get("id"))
                == str(explicit_vehicle_id)
            ),
            None,
        )

        return explicit, explicit is None

    mentioned = extract_vehicle_label(user_text)

    if mentioned:
        scored = sorted(
            (
                (
                    vehicle,
                    _vehicle_match_score(
                        vehicle,
                        mentioned,
                    ),
                )
                for vehicle in vehicles
            ),
            key=lambda item: item[1],
            reverse=True,
        )

        if scored and scored[0][1] >= 2:
            return scored[0][0], False

        return None, True

    if (
        latest_problem
        and has_automotive_content(user_text)
    ):
        match = next(
            (
                item
                for item in vehicles
                if str(item.get("id"))
                == str(
                    latest_problem.get(
                        "vehicle_id"
                    )
                )
            ),
            None,
        )

        if match:
            return match, False

    if has_automotive_content(user_text):
        if len(vehicles) == 1:
            return vehicles[0], False

        if len(vehicles) > 1:
            return None, True

    return None, False


def _problem_similarity(
    problem: dict[str, Any],
    *,
    problem_class: str,
    symptom: str,
) -> int:
    blob = " ".join(
        str(problem.get(key) or "")
        for key in (
            "title",
            "problem_class",
            "component",
            "current_conclusion",
            "next_step",
            "symptoms",
            "conditions",
            "confirmed_facts",
        )
    ).lower()

    score = 0

    if (
        str(
            problem.get("problem_class") or ""
        ).upper()
        == problem_class
    ):
        score += 3

    for token in symptom.lower().split():
        token = "".join(char for char in token if char.isalnum())
        if len(token) >= 4 and token[:7] in blob:
            score += 1

    return score


def resolve_relevant_problem(
    *,
    user_id: str | None,
    vehicle_id: str | None,
    explicit_problem_id: str | None,
    problem_class: str,
    symptom: str,
) -> dict[str, Any] | None:
    if explicit_problem_id:
        problem = repo.get_problem(
            user_id=user_id,
            problem_id=explicit_problem_id,
        )

        if (
            problem
            and vehicle_id is not None
            and str(problem.get("vehicle_id"))
            != str(vehicle_id)
        ):
            return None

        stored_class = str(
            (problem or {}).get("problem_class") or "OTHER"
        ).upper()
        if problem and problem_class not in {"OTHER", stored_class} and stored_class not in {"", "OTHER"}:
            return None
        if problem and stored_class == "OTHER" and problem_class != "OTHER":
            problem_blob = " ".join(str(problem.get(key) or "") for key in ("title", "symptoms", "conditions"))
            if classify_problem(problem_blob) != problem_class and _problem_similarity(
                problem, problem_class=problem_class, symptom=symptom,
            ) < 1:
                return None
        if problem and problem_class == "OTHER" and stored_class != "OTHER":
            if not (
                is_problem_continuation(symptom)
                or symptom_has_operating_detail(symptom)
                or _problem_similarity(problem, problem_class=problem_class, symptom=symptom) >= 1
            ):
                return None

        return problem

    candidates = repo.list_problems(
        user_id=user_id,
        vehicle_id=vehicle_id,
        statuses=repo.OPEN_PROBLEM_STATUSES,
        limit=10,
    )

    if not candidates:
        return None

    scored = sorted(
        (
            (
                item,
                _problem_similarity(
                    item,
                    problem_class=problem_class,
                    symptom=symptom,
                ),
            )
            for item in candidates
        ),
        key=lambda item: item[1],
        reverse=True,
    )

    if scored and scored[0][1] >= 2:
        best = scored[0][0]
        stored_class = str(best.get("problem_class") or "OTHER").upper()
        best_blob = " ".join(str(best.get(key) or "") for key in ("title", "symptoms", "conditions"))
        if (
            stored_class == problem_class
            or problem_class == "OTHER"
            or (stored_class == "OTHER" and classify_problem(best_blob) == problem_class)
        ):
            return best

    if (
        symptom_has_operating_detail(symptom)
        and len(candidates) == 1
        and problem_class == "OTHER"
    ):
        return candidates[0]

    if problem_class == "OTHER" and len(candidates) == 1 and is_problem_continuation(symptom):
        return candidates[0]

    return None


def _latest_problem_for_context(
    *,
    user_id: str | None,
) -> dict[str, Any] | None:
    problems = repo.list_problems(
        user_id=user_id,
        statuses=repo.OPEN_PROBLEM_STATUSES,
        limit=1,
    )

    return problems[0] if problems else None


def _natural_fallback(
    mode: str,
    language: str,
) -> str:
    ru = str(
        language or ""
    ).lower().startswith("ru")

    if mode == "META":
        if ru:
            return (
                "Я могу продолжить текущую тему, если она есть "
                "в контексте, и не буду притягивать машину "
                "к обычному разговору."
            )

        return (
            "I can continue the current topic when it is in "
            "context, without dragging a saved vehicle into "
            "normal chat."
        )

    return (
        "Привет, я на связи."
        if ru
        else "Hi, I am here."
    )


async def _natural_reply(
    context: TurnContext,
    *,
    recent_messages: list[dict[str, Any]] | None = None,
    fallback: str = "",
) -> str:
    started = time.monotonic()
    emit_event("LLM", module="conversation_orchestrator._natural_reply", operation="CONTEXT", status="STARTED", from_node="Context", to_node="LLM", input_data={"mode": context.mode, "language": context.language, "vehicle": vehicle_label(context.vehicle) if context.vehicle else "", "recent_message_count": len(recent_messages or [])})
    try:
        result = await generate_natural_chat_reply(
            mode=context.mode,
            user_text=context.text,
            language=context.language,
            recent_conversation=(
                recent_messages or []
            ),
            active_vehicle=(
                vehicle_label(context.vehicle)
                if context.vehicle
                else ""
            ),
            automotive_context=context.current_subject,
            pending_clarification=(
                context.clarification_question
            ),
            stored_facts=[],
            context_relevant=bool(
                context.vehicle
                or context.problem
            ),
        )
        emit_event("LLM", module="conversation_orchestrator._natural_reply", operation="RESULT", from_node="LLM", to_node="ANSWER", duration_ms=int((time.monotonic() - started) * 1000), output_data={"answer_excerpt": result[:300]})
        return result

    except OpenAIRouterUnavailableError:
        emit_event("LLM", module="conversation_orchestrator._natural_reply", operation="RESULT", status="WARNING", from_node="LLM", to_node="ANSWER", duration_ms=int((time.monotonic() - started) * 1000), output_data={"fallback": True})
        return fallback


def _format_internal_answer(
    language: str,
    item: dict[str, Any],
) -> str:
    summary = str(
        item.get("summary")
        or item.get("title")
        or ""
    ).strip()

    if str(
        language or ""
    ).lower().startswith("ru"):
        return (
            "По данным PULS, здесь уже есть "
            f"подходящее знание: {summary}"
        )

    return (
        "PULS already has relevant internal "
        f"knowledge for this: {summary}"
    )


def _format_research_answer(
    language: str,
    *,
    summary: str,
    links: list[dict[str, Any]],
    evidence: dict[str, Any],
    sufficient: bool,
) -> str:
    ru = str(
        language or ""
    ).lower().startswith("ru")

    evidence = evidence if isinstance(evidence, dict) else {}

    def text_values(items: Any, *keys: str) -> list[str]:
        values: list[str] = []
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict):
                value = " — ".join(
                    str(item.get(key) or "").strip()
                    for key in keys
                    if str(item.get(key) or "").strip()
                )
            else:
                value = str(item or "").strip()
            if value:
                values.append(value)
        return values

    cases = evidence.get("extracted_cases")
    probable = text_values(evidence.get("common_causes"), "cause")
    if not probable:
        probable.extend(text_values(cases, "cause"))
    checks = text_values(evidence.get("solutions"), "title", "description")
    if not checks:
        checks.extend(text_values(cases, "solution"))
    less_likely = text_values(evidence.get("unlikely_causes"))
    regional = evidence.get("regional_insights")
    findings = [
        str(value).strip()
        for value in (regional.values() if isinstance(regional, dict) else [])
        if str(value or "").strip()
    ]

    diagnosis = str(
        summary
        or evidence.get("recommendation")
        or (probable[0] if probable else "")
        or (checks[0] if checks else "")
    ).strip()
    if not diagnosis and links:
        diagnosis = (
            "Найдены релевантные материалы, но подтверждённого вывода в них пока недостаточно."
            if ru
            else "Relevant materials were found, but they do not yet support a confirmed conclusion."
        )
    if not diagnosis:
        diagnosis = (
            "Надёжных подтверждений пока недостаточно."
            if ru
            else "There is not enough reliable evidence yet."
        )

    limitations = ""
    if not sufficient:
        limitations = (
            "Вывод предварительный: доказательств недостаточно."
            if ru
            else "The conclusion is preliminary because evidence is limited."
        )
    question = str(evidence.get("clarifying_question") or "").strip()

    return format_technical_answer(
        language=language,
        diagnosis=diagnosis,
        probable_causes=probable,
        first_checks=checks,
        less_likely=less_likely,
        additional_findings=findings,
        limitations=limitations,
        links=links,
        question_tail=question,
    )


def _compact_problem_search_context(
    *, vehicle: dict[str, Any], problem: dict[str, Any], latest_clarification: str,
) -> dict[str, Any]:
    def short_list(value: Any) -> list[str]:
        return [str(item or "").strip()[:400] for item in value[:6] if str(item or "").strip()] if isinstance(value, list) else []

    conditions = problem.get("conditions")
    conditions = conditions if isinstance(conditions, dict) else {}
    return {
        "vehicle": {
            key: str(vehicle.get(key) or "")[:120]
            for key in ("make", "model", "generation", "year", "engine_code", "fuel_type", "transmission", "drivetrain")
            if vehicle.get(key) not in (None, "")
        },
        "problem": {
            "title": str(problem.get("title") or "")[:200],
            "problem_class": str(problem.get("problem_class") or "")[:80],
            "component": str(problem.get("component") or "")[:120],
            "symptoms": short_list(problem.get("symptoms")),
            "conditions": {
                str(key)[:80]: str(value or "")[:300]
                for key, value in list(conditions.items())[:8]
            },
            "confirmed_facts": short_list(problem.get("confirmed_facts")),
            "checks_summary": str(problem.get("checks_summary") or "")[:800],
            "current_conclusion": str(problem.get("current_conclusion") or "")[:800],
            "next_step": str(problem.get("next_step") or "")[:500],
        },
        "latest_clarification": str(latest_clarification or "")[:1200],
    }


def _wheel_facts_from_context(
    *, text: str, recent_messages: list[dict[str, Any]], save_requested: bool,
) -> list[Any]:
    facts = extract_wheel_spec_facts(text)
    if not save_requested:
        return facts

    # A user's explicit installed statement is actual. An assistant statement
    # is eligible only when it explicitly carries recommendation provenance.
    for item in reversed(recent_messages[-8:]):
        role = str(item.get("role") or "").lower()
        candidate = str(item.get("text") or item.get("content") or "")
        extracted = extract_wheel_spec_facts(candidate)
        if role == "user":
            facts.extend(fact for fact in extracted if fact.value_kind == "actual")
        elif role == "assistant":
            facts.extend(fact for fact in extracted if fact.value_kind == "recommended")

    # The newest exact value for each provenance/key wins. Actual and
    # recommended values intentionally remain independent.
    unique: dict[tuple[str, str], Any] = {}
    for fact in reversed(facts):
        unique.setdefault((fact.parameter_key, fact.value_kind), fact)
    return list(reversed(unique.values()))


def _stored_spec_answer(
    language: str,
    *,
    specs: dict[str, Any] | None,
    requested_keys: tuple[str, ...],
    conversation_facts: list[Any],
) -> str:
    items = (specs or {}).get("items") if isinstance(specs, dict) else []
    items = items if isinstance(items, list) else []
    wanted = set(requested_keys)
    selected = [
        item for item in items
        if not wanted or str(item.get("parameter_key") or "") in wanted
    ]
    ru = str(language or "").lower().startswith("ru")
    lines: list[str] = []
    for item in selected:
        name = str(item.get("parameter_name") or item.get("parameter_key") or "")
        actual = str(item.get("actual_value") or "").strip()
        recommended = str(item.get("recommended_value") or "").strip()
        if actual:
            lines.append(f"{name}: {actual} ({'фактически установлено' if ru else 'used on this vehicle'})")
        if recommended:
            lines.append(f"{name}: {recommended} ({'рекомендовано' if ru else 'recommended'})")
    if lines:
        return "\n".join(lines)

    remembered = [
        fact for fact in conversation_facts
        if fact.value_kind == "actual" and (not wanted or fact.parameter_key in wanted)
    ]
    if remembered:
        values = ", ".join(fact.value for fact in remembered)
        return (
            f"Вы ранее указали для этого автомобиля: {values}. Полный размер шины не подтверждён, если указан только диаметр диска."
            if ru else
            f"You previously stated for this vehicle: {values}. The full tire size is not confirmed when only the rim diameter is known."
        )
    return (
        "Для этого автомобиля подтверждённые данные о колёсах пока не сохранены."
        if ru else
        "No confirmed wheel data is stored for this vehicle yet."
    )


def _transmission_conflict(vehicle: dict[str, Any], text: str) -> bool:
    stored = " ".join(str(vehicle.get("transmission") or "").lower().split())
    lowered = " ".join(str(text or "").lower().split())
    says_manual = any(marker in stored for marker in ("manual", "механ", "мкпп"))
    says_automatic = any(
        marker in lowered
        for marker in ("акпп", "al4", "automatic", "автоматическ", "коробка автомат")
    )
    return says_manual and says_automatic


def _transmission_conflict_answer(language: str) -> str:
    if str(language or "").lower().startswith("ru"):
        return (
            "В карточке автомобиля указана механическая коробка, а в сообщении — АКПП/AL4. "
            "Уточните фактический тип коробки и при необходимости явно исправьте карточку автомобиля; "
            "до подтверждения я не буду менять сохранённую характеристику или смешивать эти данные."
        )
    return (
        "The vehicle record says manual transmission, while the message refers to an automatic/AL4. "
        "Please confirm the actual transmission and explicitly correct the vehicle record if needed; "
        "until then I will not change or combine the conflicting data."
    )


def _reference_problem_payload(
    *,
    text: str,
    vehicle: dict[str, Any],
) -> dict[str, Any]:
    title = f"{vehicle_label(vehicle)} Reference".strip()
    return {
        "title": title or text[:120],
        "problem_class": "SERVICE_REFERENCE",
        "status": "OPEN",
        "symptoms": [],
        "confirmed_facts": [],
        "hypotheses": [],
        "current_conclusion": "",
        "next_step": "",
        "mileage_start": vehicle.get("mileage"),
    }


def _associate_problem(
    *,
    user_id: str | None,
    conversation_id: str | None,
    vehicle: dict[str, Any],
    problem: dict[str, Any],
    response_context: dict[str, Any],
) -> None:
    problem_id = problem.get("id")
    if not problem_id:
        return
    repo.associate_conversation_problem(
        user_id=user_id,
        conversation_id=conversation_id,
        vehicle_id=vehicle.get("id"),
        problem_id=problem_id,
    )
    response_context.update({
        "vehicle_id": vehicle.get("id"),
        "problem_id": problem_id,
    })


def _save_user_message_and_events(
    *,
    user_id: str | None,
    conversation_id: str | None,
    vehicle: dict[str, Any],
    problem: dict[str, Any],
    text: str,
    language: str,
) -> dict[str, Any] | None:
    saved = repo.save_message(
        user_id=user_id,
        conversation_id=conversation_id,
        vehicle_id=vehicle.get("id"),
        problem_id=problem.get("id"),
        role="user",
        text=text,
        language=language,
    )
    for event in extract_technical_events(text):
        payload = dict(event)
        if (saved or {}).get("id"):
            payload["source_message_id"] = saved["id"]
        repo.create_vehicle_event(
            user_id=user_id,
            vehicle_id=vehicle.get("id"),
            problem_id=problem.get("id"),
            payload=payload,
        )
    return saved


def _problem_payload(
    *,
    symptom: str,
    problem_class: str,
    vehicle: dict[str, Any] | None,
    answer: str = "",
) -> dict[str, Any]:
    title_vehicle = vehicle_label(vehicle)

    title = " ".join(
        part
        for part in (
            title_vehicle,
            problem_class.replace(
                "_",
                " ",
            ).title(),
        )
        if part
    ).strip()

    return {
        "title": title or symptom[:120],
        "problem_class": problem_class,
        "status": "OPEN",
        "symptoms": [normalized] if (normalized := normalize_technical_symptom(symptom)) else [],
        "confirmed_facts": [],
        "hypotheses": [],
        "current_conclusion": (
            answer[:500]
            if answer
            else ""
        ),
        "next_step": "",
        "mileage_start": (
            vehicle or {}
        ).get("mileage"),
    }


def _valid_uuid(
    value: Any,
) -> str | None:
    if value in (None, ""):
        return None

    try:
        return str(
            UUID(str(value))
        )

    except (
        TypeError,
        ValueError,
        AttributeError,
    ):
        return None


def _has_bearer(
    request: Request | None,
) -> bool:
    header = (
        str(
            request.headers.get(
                "authorization"
            )
            or ""
        ).strip()
        if request is not None
        else ""
    )

    return header.lower().startswith(
        "bearer "
    )


async def process_chat_message_v2(
    payload: dict[str, Any],
    source: str = "web",
    request: Request | None = None,
) -> ChatResponse:
    text = str(
        payload.get("message")
        or payload.get("text")
        or ""
    ).strip()

    payload_language = normalize_language_code(
        payload.get("language") or "en"
    )
    message_language = detect_language(
        text,
        fallback=payload_language,
    )

    user = await get_or_create_profile(
        request=request,
        payload={
            **payload,
            "language": message_language,
        },
        require_auth=_has_bearer(request),
    )

    subscription = (
        ensure_user_subscription(
            user_id=user.id
        )
        if user.id is not None
        else None
    )

    conversation_id = _valid_uuid(
        payload.get("conversation_id")
    )

    # A new visible session must not inherit expired raw message context.
    recent_messages = repo.recent_conversation_messages(
        user_id=user.id, conversation_id=conversation_id,
    ) if conversation_id else []
    if recent_messages:
        last = datetime.fromisoformat(recent_messages[-1]["created_at"].replace("Z", "+00:00"))
        if (datetime.now(timezone.utc) - last).total_seconds() >= 12 * 60 * 60:
            conversation_id = None
            recent_messages = []
    elif conversation_id:
        conversation_id = None

    conversational_language = next(
        (
            normalize_language_code(item.get("language"))
            for item in reversed(recent_messages)
            if str(item.get("language") or "").strip()
        ),
        payload_language,
    )
    bind_trace(user_id=user.id, user_label=getattr(user, "email", None))
    emit_event("AUTH", module="conversation_orchestrator", operation="VERIFY", from_node="API", to_node="User Context", output_data={"authenticated": bool(user.id), "user_id": user.id})
    message_language = detect_language(
        text,
        fallback=conversational_language,
    )
    language = requested_response_language(text) or message_language

    vehicle_correction = extract_vehicle_correction(text)
    vehicle_spec_fact = extract_vehicle_spec_fact(text)
    vehicle_data_turn = bool(vehicle_correction or vehicle_spec_fact)

    latest_problem = (
        _latest_problem_for_context(
            user_id=user.id
        )
    )

    vehicles = repo.list_user_vehicles(
        user_id=user.id
    )
    emit_event("DATABASE", module="conversation_orchestrator", operation="READ", from_node="vehicles", to_node="Context", table_name="vehicles", affected_rows=len(vehicles), output_data={"count": len(vehicles)})

    explicit_vehicle_id = _valid_uuid(
        payload.get("vehicle_id")
    )

    explicit_problem_id = _valid_uuid(
        payload.get("problem_id")
    )

    if not text:
        return ChatResponse(
            answer="",
            links=[],
            quota=quota_payload(
                subscription
            ),
        )

    continuation_vehicle_id = next(
        (
            _valid_uuid(item.get("vehicle_id"))
            for item in reversed(recent_messages)
            if _valid_uuid(item.get("vehicle_id"))
        ),
        None,
    )
    routing_vehicle_id = explicit_vehicle_id or continuation_vehicle_id or (latest_problem or {}).get("vehicle_id")
    routing_vehicle = next(
        (item for item in vehicles if str(item.get("id")) == str(routing_vehicle_id)),
        vehicles[0] if len(vehicles) == 1 else None,
    )

    semantic_intent = await classify_turn_intent(
        user_text=text,
        language=language,
        recent_conversation=recent_messages,
        active_vehicle=vehicle_label(routing_vehicle),
        active_problem=" ".join(
            str((latest_problem or {}).get(key) or "")
            for key in ("title", "problem_class", "component", "symptoms", "current_conclusion")
        )[:500],
    )
    semantic_kind = str(getattr(semantic_intent, "intent", "") or "").upper()
    bind_trace(intent=semantic_kind)
    emit_event("CLASSIFIER", module="conversation_orchestrator", operation="RESULT", from_node="Context", to_node="Classifier", edge_label=semantic_kind or "UNKNOWN", output_data={"intent": semantic_kind, "external_search": bool(getattr(semantic_intent, "external_search", False)), "topic_changed": bool(getattr(semantic_intent, "topic_changed", False)), "vehicle_spec_action": getattr(semantic_intent, "vehicle_spec_action", "NONE")})
    relevant_recent_messages = (
        [] if bool(getattr(semantic_intent, "topic_changed", False)) else recent_messages
    )
    vehicle_spec_action = str(getattr(semantic_intent, "vehicle_spec_action", "NONE") or "NONE").upper()
    semantic_spec_turn = vehicle_spec_action in {"LOOKUP", "SAVE"}
    vehicle_data_turn = vehicle_data_turn or semantic_spec_turn
    semantic_reference = bool(
        semantic_intent
        and semantic_intent.external_search
        and semantic_kind in {"REFERENCE", "HOWTO"}
    )

    mode = "GENERAL_CHAT"

    if semantic_kind == "META" or (not semantic_intent and looks_like_meta_question(text)):
        mode = "META_CHAT"

    elif vehicle_data_turn or semantic_kind in {"DIAGNOSTIC", "REFERENCE", "HOWTO"} or has_automotive_content(text) or (
        is_problem_continuation(text)
        and (explicit_problem_id or conversation_id or latest_problem)
    ):
        mode = "AUTOMOTIVE"

    vehicle, ambiguous_vehicle = (
        resolve_relevant_vehicle(
            vehicles=vehicles,
            explicit_vehicle_id=(explicit_vehicle_id or continuation_vehicle_id),
            user_text=text,
            latest_problem=latest_problem,
        )
    )
    if vehicle_data_turn and vehicle is None and not ambiguous_vehicle and len(vehicles) == 1:
        vehicle = vehicles[0]

    if semantic_reference and vehicle is None and not ambiguous_vehicle and len(vehicles) == 1:
        vehicle = vehicles[0]

    reference_request = semantic_reference
    problem_class = classify_problem(text)

    problem = None
    if mode == "AUTOMOTIVE" and not reference_request and not vehicle_data_turn:
        problem = resolve_relevant_problem(
            user_id=user.id,
            vehicle_id=(vehicle or {}).get("id"),
            explicit_problem_id=explicit_problem_id,
            problem_class=problem_class,
            symptom=text,
        )

    conversation = (
        repo.get_or_create_conversation(
            user_id=user.id,
            vehicle_id=(
                vehicle or {}
            ).get("id"),
            problem_id=(
                problem or {}
            ).get("id"),
            title=text,
            conversation_id=conversation_id,
        )
    )

    conversation_id = (
        conversation or {}
    ).get("id")
    bind_trace(conversation_id=conversation_id, vehicle_id=(conversation or {}).get("vehicle_id"), problem_id=(conversation or {}).get("problem_id"))
    emit_event("CONTEXT", module="conversation_orchestrator", operation="RESULT", from_node="Classifier", to_node="Conversation", table_name="conversations", record_id=conversation_id, output_data={"mode": mode, "vehicle_id": (conversation or {}).get("vehicle_id"), "problem_id": (conversation or {}).get("problem_id")})

    # The existing Conversation is itself canonical context. A clarification
    # may omit problem_id in the request while still belonging to its Problem.
    if (
        mode == "AUTOMOTIVE"
        and not reference_request
        and problem is None
        and (conversation or {}).get("problem_id")
    ):
        conversation_problem = repo.get_problem(
            user_id=user.id,
            problem_id=conversation.get("problem_id"),
        )
        if (
            conversation_problem
            and str(conversation_problem.get("vehicle_id")) == str((vehicle or {}).get("id"))
            and (
                str(conversation_problem.get("problem_class") or "").upper() == problem_class
                or symptom_has_operating_detail(text)
                or is_problem_continuation(text)
                or (
                    str(conversation_problem.get("problem_class") or "").upper() == "OTHER"
                    and classify_problem(" ".join(str(conversation_problem.get(key) or "") for key in ("title", "symptoms", "conditions"))) == problem_class
                )
            )
        ):
            problem = conversation_problem

    response_context = {
        "conversation_id": conversation_id,
        "vehicle_id": (conversation or {}).get("vehicle_id"),
        "problem_id": (conversation or {}).get("problem_id"),
    }

    context = TurnContext(
        mode=mode,
        language=language,
        text=text,
        vehicle=vehicle,
        problem=problem,
        current_subject=(
            text
            if mode == "AUTOMOTIVE"
            else ""
        ),
        symptom=(
            text
            if mode == "AUTOMOTIVE"
            else ""
        ),
        problem_class=problem_class,
    )

    # ---------------------------------------------------------------
    # General / social / meta chat.
    # Persist only raw conversation and messages.
    # Do not create diagnostic/search artifacts.
    # ---------------------------------------------------------------

    if mode in {
        "GENERAL_CHAT",
        "META_CHAT",
    }:
        fallback = _natural_fallback(
            (
                "META"
                if mode == "META_CHAT"
                else "GENERAL"
            ),
            language,
        )

        context.vehicle = (
            vehicle
            if mode == "META_CHAT"
            else None
        )

        context.problem = (
            problem
            if mode == "META_CHAT"
            else None
        )

        answer = plain_text_response(
            await _natural_reply(
                context,
                recent_messages=relevant_recent_messages,
                fallback=fallback,
            )
        )

        repo.save_message(
            user_id=user.id,
            conversation_id=conversation_id,
            vehicle_id=None,
            problem_id=None,
            role="user",
            text=text,
            language=message_language,
        )

        repo.save_message(
            user_id=user.id,
            conversation_id=conversation_id,
            vehicle_id=None,
            problem_id=None,
            role="assistant",
            text=answer,
            language=language,
        )

        return ChatResponse(**response_context,
            answer=answer,
            links=[],
            quota=quota_payload(
                subscription
            ),
        )

    # ---------------------------------------------------------------
    # Vehicle clarification.
    # ---------------------------------------------------------------

    if ambiguous_vehicle:
        context.clarification_question = (
            clarification_for(
                language,
                missing="vehicle",
            )
        )

        answer = plain_text_response(
            await _natural_reply(
                context,
                fallback=(
                    context.clarification_question
                ),
            )
        )

        repo.save_message(
            user_id=user.id,
            conversation_id=conversation_id,
            role="user",
            text=text,
            language=message_language,
        )

        repo.save_message(
            user_id=user.id,
            conversation_id=conversation_id,
            role="assistant",
            text=answer,
            language=language,
        )

        return ChatResponse(**response_context,
            answer=answer,
            links=[],
            quota=quota_payload(
                subscription
            ),
        )

    if vehicle is None:
        context.clarification_question = (
            clarification_for(
                language,
                missing="vehicle",
            )
        )

        answer = plain_text_response(
            await _natural_reply(
                context,
                fallback=(
                    context.clarification_question
                ),
            )
        )

        repo.save_message(
            user_id=user.id,
            conversation_id=conversation_id,
            role="user",
            text=text,
            language=message_language,
        )

        repo.save_message(
            user_id=user.id,
            conversation_id=conversation_id,
            role="assistant",
            text=answer,
            language=language,
        )

        return ChatResponse(**response_context,
            answer=answer,
            links=[],
            quota=quota_payload(
                subscription
            ),
        )

    if vehicle_correction:
        try:
            persistence = persist_vehicle_correction(
                user_id=user.id,
                vehicle_id=vehicle.get("id"),
                values=vehicle_correction,
            )
        except (SupabaseOperationError, SupabaseUnavailableError):
            persistence = {"status": "failed"}
        changed = persistence.get("status") == "saved"
        transmission = str(vehicle_correction.get("transmission") or "")
        transmission_ru = "Автомат" if transmission == "Automatic" else "Механика"
        if str(language or "").lower().startswith("ru"):
            answer = (
                f"Тип коробки передач изменён на «{transmission_ru}»."
                if changed else
                "Не удалось сохранить изменение типа коробки передач. Карточка автомобиля не изменена."
            )
        else:
            answer = (
                f"The transmission was changed to {transmission}."
                if changed else
                "The transmission change could not be saved. The vehicle card was not changed."
            )
        repo.save_message(
            user_id=user.id, conversation_id=conversation_id, vehicle_id=vehicle.get("id"),
            problem_id=None, role="user", text=text, language=message_language,
        )
        repo.save_message(
            user_id=user.id, conversation_id=conversation_id, vehicle_id=vehicle.get("id"),
            problem_id=None, role="assistant", text=answer, language=language,
        )
        return ChatResponse(**response_context, answer=answer, links=[], quota=quota_payload(subscription))

    wheel_context_facts = _wheel_facts_from_context(
        text=text,
        recent_messages=recent_messages,
        save_requested=vehicle_spec_action == "SAVE",
    )
    requested_spec_keys = tuple(getattr(semantic_intent, "vehicle_spec_keys", ()) or ())

    if vehicle_spec_action == "LOOKUP":
        answer = _stored_spec_answer(
            language,
            specs=repo.get_vehicle_specs(user_id=user.id, vehicle_id=vehicle.get("id")),
            requested_keys=requested_spec_keys,
            conversation_facts=_wheel_facts_from_context(
                text=text, recent_messages=recent_messages, save_requested=True,
            ),
        )
        repo.save_message(
            user_id=user.id, conversation_id=conversation_id, vehicle_id=vehicle.get("id"),
            problem_id=None, role="user", text=text, language=message_language,
        )
        repo.save_message(
            user_id=user.id, conversation_id=conversation_id, vehicle_id=vehicle.get("id"),
            problem_id=None, role="assistant", text=answer, language=language,
        )
        return ChatResponse(**response_context, answer=answer, links=[], quota=quota_payload(subscription))

    facts_to_save = wheel_context_facts or ([vehicle_spec_fact] if vehicle_spec_fact else [])
    if requested_spec_keys:
        facts_to_save = [fact for fact in facts_to_save if fact.parameter_key in set(requested_spec_keys)]

    if vehicle_spec_action == "SAVE" and not facts_to_save:
        answer = (
            "Не удалось определить точное подтверждённое значение. Данные не сохранены — укажите точный размер или давление."
            if str(language or "").lower().startswith("ru") else
            "No exact confirmed value could be identified. Nothing was saved; please provide the exact size or pressure."
        )
        repo.save_message(
            user_id=user.id, conversation_id=conversation_id, vehicle_id=vehicle.get("id"),
            problem_id=None, role="user", text=text, language=message_language,
        )
        repo.save_message(
            user_id=user.id, conversation_id=conversation_id, vehicle_id=vehicle.get("id"),
            problem_id=None, role="assistant", text=answer, language=language,
        )
        return ChatResponse(**response_context, answer=answer, links=[], quota=quota_payload(subscription))

    if facts_to_save:
        results: list[tuple[Any, dict[str, Any]]] = []
        for fact in facts_to_save:
            try:
                result = persist_vehicle_spec_fact(
                    user_id=user.id,
                    vehicle_id=vehicle.get("id"),
                    fact=fact,
                )
            except (SupabaseOperationError, SupabaseUnavailableError):
                result = {"status": "failed"}
            results.append((fact, result))

        conflict = next(((fact, result) for fact, result in results if result.get("status") == "conflict"), None)
        saved_facts = [fact for fact, result in results if result.get("status") == "saved"]
        failed = [fact for fact, result in results if result.get("status") == "failed"]
        if conflict:
            _, result = conflict
            answer = (
                f"Сейчас сохранено «{result['existing']}». Подтвердите, что нужно заменить на «{result['requested']}»."
                if str(language or "").lower().startswith("ru") else
                f"The saved value is {result['existing']}. Please confirm replacing it with {result['requested']}."
            )
        elif failed:
            answer = (
                "Не удалось сохранить и подтвердить все параметры. Неподтверждённые значения не считаются добавленными в карточку."
                if str(language or "").lower().startswith("ru") else
                "Saving all parameters could not be verified. Unverified values are not reported as added to the vehicle card."
            )
        else:
            values = ", ".join(fact.value for fact in saved_facts)
            actual_only = all(fact.value_kind == "actual" for fact in saved_facts)
            if str(language or "").lower().startswith("ru"):
                answer = (
                    f"Сохранил «{values}» как фактически используемое на автомобиле."
                    if actual_only else
                    f"Сохранил проверенные значения: {values}. Фактические данные и рекомендованную спецификацию записал раздельно."
                )
            else:
                answer = (
                    f"Saved {values} as used on this vehicle."
                    if actual_only else
                    f"Saved the verified values: {values}. Actual and recommended data were stored separately."
                )
        repo.save_message(
            user_id=user.id, conversation_id=conversation_id, vehicle_id=vehicle.get("id"),
            problem_id=None, role="user", text=text, language=message_language,
        )
        repo.save_message(
            user_id=user.id, conversation_id=conversation_id, vehicle_id=vehicle.get("id"),
            problem_id=None, role="assistant", text=answer, language=language,
        )
        return ChatResponse(**response_context, answer=answer, links=[], quota=quota_payload(subscription))

    # A stored manual transmission and an automatic/AL4 report are mutually
    # inconsistent. Preserve the canonical vehicle record and clarify first.
    if (
        not reference_request
        and is_factual_technical_statement(text)
        and _transmission_conflict(vehicle, text)
    ):
        answer = _transmission_conflict_answer(language)
        repo.save_message(
            user_id=user.id,
            conversation_id=conversation_id,
            vehicle_id=vehicle.get("id"),
            problem_id=None,
            role="user",
            text=text,
            language=message_language,
        )
        repo.save_message(
            user_id=user.id,
            conversation_id=conversation_id,
            vehicle_id=vehicle.get("id"),
            problem_id=None,
            role="assistant",
            text=answer,
            language=language,
        )
        return ChatResponse(**response_context,
            answer=answer,
            links=[],
            quota=quota_payload(subscription),
        )

    # Vehicle-aware chat that establishes no technical fact stays raw.
    if not reference_request and not is_factual_technical_statement(text):
        context.problem = None
        answer = plain_text_response(
            await _natural_reply(
                context,
                recent_messages=relevant_recent_messages,
                fallback=_natural_fallback("GENERAL", language),
            )
        )
        repo.save_message(
            user_id=user.id,
            conversation_id=conversation_id,
            vehicle_id=vehicle.get("id"),
            problem_id=None,
            role="user",
            text=text,
            language=message_language,
        )
        repo.save_message(
            user_id=user.id,
            conversation_id=conversation_id,
            vehicle_id=vehicle.get("id"),
            problem_id=None,
            role="assistant",
            text=answer,
            language=language,
        )
        return ChatResponse(**response_context,
            answer=answer,
            links=[],
            quota=quota_payload(subscription),
        )

    # HOWTO/REFERENCE may use the vehicle, but never the active diagnostic
    # Problem. A separate reference owner is required by the frozen Search FK.
    if reference_request:
        reference_problem = None
        conversation_problem_id = (conversation or {}).get("problem_id")
        if conversation_problem_id:
            candidate = repo.get_problem(user_id=user.id, problem_id=conversation_problem_id)
            if (
                candidate
                and str(candidate.get("vehicle_id")) == str(vehicle.get("id"))
                and str(candidate.get("problem_class") or "").upper() == "SERVICE_REFERENCE"
            ):
                reference_problem = candidate
        if reference_problem is None:
            reference_problem = resolve_relevant_problem(
                user_id=user.id,
                vehicle_id=vehicle.get("id"),
                explicit_problem_id=None,
                problem_class="SERVICE_REFERENCE",
                symptom=str(getattr(semantic_intent, "resolved_query", "") or text),
            )
        if reference_problem is None:
            reference_problem = repo.save_problem(
                user_id=user.id,
                vehicle_id=vehicle.get("id"),
                payload=_reference_problem_payload(text=text, vehicle=vehicle),
            )

        reference_context = _compact_problem_search_context(
            vehicle=vehicle,
            problem=reference_problem or {},
            latest_clarification=text,
        )
        reference_context["request"] = {
            "source_preference": str(getattr(semantic_intent, "source_preference", "ANY")),
            "visual_requested": bool(getattr(semantic_intent, "visual_requested", False)),
            "link_requested": bool(getattr(semantic_intent, "link_requested", False)),
        }

        research = await run_search_stages(
            user_id=user.id,
            vehicle_id=vehicle.get("id"),
            problem_id=(reference_problem or {}).get("id"),
            conversation_id=conversation_id,
            trigger_type="HOWTO" if semantic_kind == "HOWTO" else "REFERENCE",
            allow_reuse=bool(getattr(semantic_intent, "continues_previous_request", False)),
            vehicle_label=vehicle_label(vehicle),
            query=str(getattr(semantic_intent, "resolved_query", "") or text),
            language=language,
            problem_context=reference_context,
        )
        visual_requested = bool(getattr(semantic_intent, "visual_requested", False))
        image_links = [
            item for item in research.links
            if str(item.get("type") or "").lower() in {"image", "photo", "picture"}
        ]
        if visual_requested and not image_links:
            if research.links:
                source_url = str(research.links[0].get("url") or "").strip()
                answer = (
                    f"Надёжный прямой URL изображения получить не удалось. Вот страница-источник: {source_url}"
                    if str(language or "").lower().startswith("ru") else
                    f"A reliable direct image URL was not retrieved. Here is the source page: {source_url}"
                )
            else:
                answer = (
                    "Надёжное изображение по этому запросу не найдено."
                    if str(language or "").lower().startswith("ru") else
                    "No reliable image was found for this request."
                )
        else:
            answer = plain_text_response(
                _format_research_answer(
                    language,
                    summary=research.summary,
                    links=research.links,
                    evidence=getattr(research, "evidence", {}),
                    sufficient=research.sufficient,
                )
            )
        repo.save_message(
            user_id=user.id,
            conversation_id=conversation_id,
            vehicle_id=vehicle.get("id"),
            problem_id=None,
            role="user",
            text=text,
            language=message_language,
        )
        repo.save_message(
            user_id=user.id,
            conversation_id=conversation_id,
            vehicle_id=vehicle.get("id"),
            problem_id=None,
            role="assistant",
            text=answer,
            language=language,
        )
        return ChatResponse(**response_context,
            answer=answer,
            links=research.links,
            quota=quota_payload(research.quota or subscription),
        )

    # ---------------------------------------------------------------
    # Initial symptom without enough operating detail.
    # ---------------------------------------------------------------

    if (
        not symptom_has_operating_detail(text)
        and problem is None
    ):
        context.clarification_question = (
            clarification_for(
                language,
                missing="symptom",
                problem_class=problem_class,
            )
        )

        problem = repo.save_problem(
            user_id=user.id,
            vehicle_id=vehicle.get("id"),
            payload=_problem_payload(
                symptom=text,
                problem_class=problem_class,
                vehicle=vehicle,
            ),
        )

        context.problem = problem
        _associate_problem(
            user_id=user.id,
            conversation_id=conversation_id,
            vehicle=vehicle,
            problem=problem or {},
            response_context=response_context,
        )

        answer = plain_text_response(
            await _natural_reply(
                context,
                fallback=(
                    context.clarification_question
                ),
            )
        )

        _save_user_message_and_events(
            user_id=user.id,
            conversation_id=conversation_id,
            vehicle=vehicle,
            problem=problem or {},
            text=text,
            language=message_language,
        )

        repo.save_message(
            user_id=user.id,
            conversation_id=conversation_id,
            vehicle_id=vehicle.get("id"),
            problem_id=(
                problem or {}
            ).get("id"),
            role="assistant",
            text=answer,
            language=language,
        )

        return ChatResponse(**response_context,
            answer=answer,
            links=[],
            quota=quota_payload(
                subscription
            ),
        )

    # ---------------------------------------------------------------
    # Create or update active diagnostic problem.
    # ---------------------------------------------------------------

    problem_created_this_turn = False
    if problem is None:
        problem = repo.save_problem(
            user_id=user.id,
            vehicle_id=vehicle.get("id"),
            payload=_problem_payload(
                symptom=text,
                problem_class=problem_class,
                vehicle=vehicle,
            ),
        )

        context.problem = problem
        problem_created_this_turn = True

    else:
        current_symptoms = merge_problem_symptoms(problem.get("symptoms"), text)
        stored_class = str(problem.get("problem_class") or "OTHER").upper()
        class_upgrade = stored_class == "OTHER" and problem_class != "OTHER"

        updated_problem = repo.save_problem(
            user_id=user.id,
            vehicle_id=vehicle.get("id"),
            problem_id=problem.get("id"),
            payload={
                "status": (
                    problem.get("status")
                    or "OPEN"
                ),
                "symptoms": current_symptoms,
                **({
                    "problem_class": problem_class,
                    "title": " ".join((vehicle_label(vehicle), problem_class.replace("_", " ").title())).strip(),
                } if class_upgrade else {}),
            },
        )

        if updated_problem:
            problem = updated_problem
            context.problem = problem

    _associate_problem(
        user_id=user.id,
        conversation_id=conversation_id,
        vehicle=vehicle,
        problem=problem or {},
        response_context=response_context,
    )
    bind_trace(vehicle_id=vehicle.get("id"), problem_id=(problem or {}).get("id"), conversation_id=conversation_id)
    emit_event("PROBLEM", module="conversation_orchestrator", operation="CONTEXT", from_node="Conversation", to_node="Problem", table_name="problems", record_id=str((problem or {}).get("id") or "") or None, output_data={"problem_class": (problem or {}).get("problem_class"), "status": (problem or {}).get("status")})

    # ---------------------------------------------------------------
    # Internal PULS knowledge.
    # ---------------------------------------------------------------

    knowledge = repo.find_relevant_knowledge(
        vehicle=vehicle,
        symptom=text,
        limit=3,
    )
    emit_event("KNOWLEDGE", module="conversation_orchestrator", operation="READ", from_node="Context", to_node="Knowledge", edge_label="HIT" if knowledge else "MISS", table_name="knowledge_items", affected_rows=len(knowledge), output_data={"state": "HIT" if knowledge else "MISS", "count": len(knowledge)})

    if knowledge:
        answer = plain_text_response(
            _format_internal_answer(
                language,
                knowledge[0],
            )
        )

        _save_user_message_and_events(
            user_id=user.id,
            conversation_id=conversation_id,
            vehicle=vehicle,
            problem=problem or {},
            text=text,
            language=message_language,
        )

        repo.save_message(
            user_id=user.id,
            conversation_id=conversation_id,
            vehicle_id=vehicle.get("id"),
            problem_id=(
                problem or {}
            ).get("id"),
            role="assistant",
            text=answer,
            language=language,
        )

        return ChatResponse(**response_context,
            answer=answer,
            links=[],
            quota=quota_payload(
                subscription
            ),
        )

    # A new diagnostic Problem gets one Fast Chat turn before paid external
    # research. Later turns can enter Search with the accumulated context.
    if problem_created_this_turn:
        context.clarification_question = clarification_for(
            language,
            missing="symptom",
            problem_class=problem_class,
        )
        answer = plain_text_response(
            await _natural_reply(
                context,
                recent_messages=relevant_recent_messages,
                fallback=context.clarification_question,
            )
        )
        _save_user_message_and_events(
            user_id=user.id,
            conversation_id=conversation_id,
            vehicle=vehicle,
            problem=problem or {},
            text=text,
            language=message_language,
        )
        repo.save_message(
            user_id=user.id,
            conversation_id=conversation_id,
            vehicle_id=vehicle.get("id"),
            problem_id=(problem or {}).get("id"),
            role="assistant",
            text=answer,
            language=language,
        )
        return ChatResponse(
            **response_context,
            answer=answer,
            links=[],
            quota=quota_payload(subscription),
        )

    # ---------------------------------------------------------------
    # External staged research.
    # ---------------------------------------------------------------

    research = await run_search_stages(
        user_id=user.id,
        vehicle_id=vehicle.get("id"),
        problem_id=(
            problem or {}
        ).get("id"),
        vehicle_label=vehicle_label(
            vehicle
        ),
        query=text,
        language=language,
        problem_context=_compact_problem_search_context(
            vehicle=vehicle,
            problem=problem or {},
            latest_clarification=text,
        ),
        conversation_id=conversation_id,
        trigger_type="DIAGNOSTIC",
    )
    answer = plain_text_response(
        _format_research_answer(
            language,
            summary=research.summary,
            links=research.links,
            evidence=getattr(research, "evidence", {}),
            sufficient=research.sufficient,
        )
    )

    conclusion = str(research.summary or "").strip()
    episode_trigger = str((getattr(research, "episode", None) or {}).get("trigger_type") or "DIAGNOSTIC").upper()
    if problem and conclusion and episode_trigger == "DIAGNOSTIC":
        updated_problem = repo.save_problem(
            user_id=user.id,
            vehicle_id=vehicle.get("id"),
            problem_id=problem.get("id"),
            payload={
                "current_conclusion": conclusion,
                "status": "OPEN",
            },
        )

        if updated_problem:
            problem = updated_problem
            context.problem = problem

    _save_user_message_and_events(
        user_id=user.id,
        conversation_id=conversation_id,
        vehicle=vehicle,
        problem=problem or {},
        text=text,
        language=message_language,
    )

    repo.save_message(
        user_id=user.id,
        conversation_id=conversation_id,
        vehicle_id=vehicle.get("id"),
        problem_id=(
            problem or {}
        ).get("id"),
        role="assistant",
        text=answer,
        language=language,
    )

    return ChatResponse(**response_context,
        answer=answer,
        links=research.links,
        quota=quota_payload(
            research.quota
            or subscription
        ),
    )
