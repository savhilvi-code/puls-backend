from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import Request

from app.schemas.chat import ChatResponse
from app.services.auth_service import get_or_create_profile
from app.services.openai_service import OpenAIRouterUnavailableError, generate_natural_chat_reply
from app.services.search_stage_service import run_search_stages
from app.services.subscription_service import ensure_user_subscription, quota_payload
from app.services.v2_context import (
    TurnContext,
    clarification_for,
    classify_problem,
    extract_technical_events,
    extract_vehicle_label,
    has_automotive_content,
    is_social_general_text,
    looks_like_meta_question,
    plain_text_response,
    symptom_has_operating_detail,
    vehicle_label,
)
from app.services import v2_repository as repo


def _vehicle_match_score(vehicle: dict[str, Any], car_text: str) -> int:
    text = " ".join(str(car_text or "").lower().split())
    if not text:
        return 0
    score = 0
    for key, weight in (("brand", 4), ("model", 4), ("engine", 2), ("year", 2), ("nickname", 3), ("vin", 5)):
        value = str(vehicle.get(key) or "").lower().strip()
        if not value:
            continue
        if value in text:
            score += weight
        elif any(part and part in text for part in value.replace("-", " ").split()):
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
        explicit = next((item for item in vehicles if item.get("id") == explicit_vehicle_id), None)
        return explicit, explicit is None

    mentioned = extract_vehicle_label(user_text)
    if mentioned:
        scored = sorted(((vehicle, _vehicle_match_score(vehicle, mentioned)) for vehicle in vehicles), key=lambda item: item[1], reverse=True)
        if scored and scored[0][1] >= 2:
            return scored[0][0], False
        return None, True

    if latest_problem and has_automotive_content(user_text):
        match = next((item for item in vehicles if item.get("id") == latest_problem.get("vehicle_id")), None)
        if match:
            return match, False

    if has_automotive_content(user_text):
        if len(vehicles) == 1:
            return vehicles[0], False
        if len(vehicles) > 1:
            return None, True
    return None, False


def _problem_similarity(problem: dict[str, Any], *, problem_class: str, symptom: str) -> int:
    blob = " ".join(
        str(problem.get(key) or "")
        for key in ("title", "problem_class", "component", "current_conclusion", "next_step")
    ).lower()
    score = 0
    if str(problem.get("problem_class") or "").upper() == problem_class:
        score += 3
    for token in symptom.lower().split():
        if len(token) >= 5 and token in blob:
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
        return repo.get_problem(user_id=user_id, problem_id=explicit_problem_id)
    candidates = repo.list_problems(user_id=user_id, vehicle_id=vehicle_id, statuses=repo.OPEN_PROBLEM_STATUSES, limit=10)
    if not candidates:
        return None
    scored = sorted(((item, _problem_similarity(item, problem_class=problem_class, symptom=symptom)) for item in candidates), key=lambda item: item[1], reverse=True)
    if scored and scored[0][1] >= 2:
        return scored[0][0]
    return candidates[0] if symptom_has_operating_detail(symptom) and len(candidates) == 1 else None


def _latest_problem_for_context(*, user_id: str | None) -> dict[str, Any] | None:
    problems = repo.list_problems(user_id=user_id, statuses=repo.OPEN_PROBLEM_STATUSES, limit=1)
    return problems[0] if problems else None


def _natural_fallback(mode: str, language: str) -> str:
    ru = str(language or "").lower().startswith("ru")
    if mode == "META":
        return "Я могу продолжить текущую тему, если она есть в контексте, и не буду притягивать машину к обычному разговору." if ru else "I can continue the current topic when it is in context, without dragging a saved vehicle into normal chat."
    return "Привет, я на связи." if ru else "Hi, I am here."


async def _natural_reply(context: TurnContext, *, recent_messages: list[dict[str, Any]] | None = None, fallback: str = "") -> str:
    try:
        return await generate_natural_chat_reply(
            mode=context.mode,
            user_text=context.text,
            language=context.language,
            recent_conversation=recent_messages or [],
            active_vehicle=vehicle_label(context.vehicle) if context.vehicle else "",
            automotive_context=context.current_subject,
            pending_clarification=context.clarification_question,
            stored_facts=[],
            context_relevant=bool(context.vehicle or context.problem),
        )
    except OpenAIRouterUnavailableError:
        return fallback


def _format_internal_answer(language: str, item: dict[str, Any]) -> str:
    summary = str(item.get("summary") or item.get("content") or item.get("title") or "").strip()
    if str(language or "").lower().startswith("ru"):
        return f"По данным PULS, здесь уже есть подходящее знание: {summary}"
    return f"PULS already has relevant internal knowledge for this: {summary}"


def _format_research_answer(language: str, *, summary: str, links: list[dict[str, Any]], sufficient: bool) -> str:
    ru = str(language or "").lower().startswith("ru")
    if not summary:
        return (
            "Я запустил исследование, но надежных подтверждений пока недостаточно. Лучше уточнить симптом или условия проявления."
            if ru
            else "I ran the research stage, but there is not enough reliable evidence yet. It would be better to narrow the symptom or operating conditions."
        )
    prefix = "По найденным источникам:" if ru else "Based on the evidence found:"
    confidence = "Этого достаточно для следующего шага." if ru and sufficient else "This is enough for the next step." if sufficient else "Evidence is still limited."
    source_text = ""
    if links:
        source_text = "\n\n" + "\n".join(f"{item.get('title') or item.get('url')}: {item.get('url')}" for item in links[:4] if item.get("url"))
    return f"{prefix} {summary}\n\n{confidence}{source_text}"


def _problem_payload(*, symptom: str, problem_class: str, vehicle: dict[str, Any] | None, answer: str = "") -> dict[str, Any]:
    title_vehicle = vehicle_label(vehicle)
    title = " ".join(part for part in (title_vehicle, problem_class.replace("_", " ").title()) if part).strip()
    return {
        "title": title or symptom[:120],
        "problem_class": problem_class,
        "status": "OPEN",
        "symptoms": [symptom],
        "confirmed_facts": [],
        "hypotheses": [],
        "current_conclusion": answer[:500] if answer else "",
        "next_step": "",
        "mileage": (vehicle or {}).get("mileage"),
    }


def _valid_uuid(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return None


def _has_bearer(request: Request | None) -> bool:
    header = str(request.headers.get("authorization") or "").strip() if request is not None else ""
    return header.lower().startswith("bearer ")


async def process_chat_message_v2(payload: dict[str, Any], source: str = "web", request: Request | None = None) -> ChatResponse:
    text = str(payload.get("message") or payload.get("text") or "").strip()
    language = str(payload.get("language") or "en")
    user = await get_or_create_profile(request=request, payload={**payload, "language": language}, require_auth=_has_bearer(request))
    subscription = ensure_user_subscription(user_id=user.id) if user.id is not None else None
    conversation_id = _valid_uuid(payload.get("conversation_id"))
    recent_messages = repo.recent_conversation_messages(user_id=user.id, conversation_id=conversation_id)

    latest_problem = _latest_problem_for_context(user_id=user.id)
    vehicles = repo.list_user_vehicles(user_id=user.id)
    explicit_vehicle_id = _valid_uuid(payload.get("vehicle_id"))
    explicit_problem_id = _valid_uuid(payload.get("problem_id"))

    if not text:
        return ChatResponse(answer="", links=[], quota=quota_payload(subscription))

    mode = "GENERAL_CHAT"
    if looks_like_meta_question(text):
        mode = "META_CHAT"
    elif has_automotive_content(text):
        mode = "AUTOMOTIVE"

    vehicle, ambiguous_vehicle = resolve_relevant_vehicle(
        vehicles=vehicles,
        explicit_vehicle_id=explicit_vehicle_id,
        user_text=text,
        latest_problem=latest_problem,
    )
    problem_class = classify_problem(text)
    problem = resolve_relevant_problem(
        user_id=user.id,
        vehicle_id=(vehicle or {}).get("id"),
        explicit_problem_id=explicit_problem_id,
        problem_class=problem_class,
        symptom=text,
    )

    conversation = repo.get_or_create_conversation(
        user_id=user.id,
        vehicle_id=(vehicle or {}).get("id"),
        problem_id=(problem or {}).get("id"),
        title=text,
        conversation_id=conversation_id,
    )
    conversation_id = (conversation or {}).get("id")

    context = TurnContext(
        mode=mode,
        language=language,
        text=text,
        vehicle=vehicle,
        problem=problem,
        current_subject=text if mode == "AUTOMOTIVE" else "",
        symptom=text if mode == "AUTOMOTIVE" else "",
        problem_class=problem_class,
    )

    if mode in {"GENERAL_CHAT", "META_CHAT"} or is_social_general_text(text):
        fallback = _natural_fallback("META" if mode == "META_CHAT" else "GENERAL", language)
        context.vehicle = vehicle if mode == "META_CHAT" else None
        context.problem = problem if mode == "META_CHAT" else None
        answer = plain_text_response(await _natural_reply(context, recent_messages=recent_messages if mode == "META_CHAT" else [], fallback=fallback))
        repo.save_message(user_id=user.id, conversation_id=conversation_id, vehicle_id=None, problem_id=None, role="user", text=text, language=language)
        repo.save_message(user_id=user.id, conversation_id=conversation_id, vehicle_id=None, problem_id=None, role="assistant", text=answer, language=language)
        return ChatResponse(answer=answer, links=[], quota=quota_payload(subscription))

    if ambiguous_vehicle:
        context.clarification_question = clarification_for(language, missing="vehicle")
        answer = plain_text_response(await _natural_reply(context, fallback=context.clarification_question))
        repo.save_message(user_id=user.id, conversation_id=conversation_id, role="user", text=text, language=language)
        repo.save_message(user_id=user.id, conversation_id=conversation_id, role="assistant", text=answer, language=language)
        return ChatResponse(answer=answer, links=[], quota=quota_payload(subscription))

    if vehicle is None:
        context.clarification_question = clarification_for(language, missing="vehicle")
        answer = plain_text_response(await _natural_reply(context, fallback=context.clarification_question))
        repo.save_message(user_id=user.id, conversation_id=conversation_id, role="user", text=text, language=language)
        repo.save_message(user_id=user.id, conversation_id=conversation_id, role="assistant", text=answer, language=language)
        return ChatResponse(answer=answer, links=[], quota=quota_payload(subscription))

    if not symptom_has_operating_detail(text) and problem is None:
        context.clarification_question = clarification_for(language, missing="symptom", problem_class=problem_class)
        problem = repo.save_problem(
            user_id=user.id,
            vehicle_id=vehicle.get("id"),
            payload=_problem_payload(symptom=text, problem_class=problem_class, vehicle=vehicle),
        )
        context.problem = problem
        for event in extract_technical_events(text):
            repo.create_vehicle_event(user_id=user.id, vehicle_id=vehicle.get("id"), problem_id=(problem or {}).get("id"), payload=event)
        answer = plain_text_response(await _natural_reply(context, fallback=context.clarification_question))
        repo.save_message(user_id=user.id, conversation_id=conversation_id, vehicle_id=vehicle.get("id"), problem_id=(problem or {}).get("id"), role="user", text=text, language=language)
        repo.save_message(user_id=user.id, conversation_id=conversation_id, vehicle_id=vehicle.get("id"), problem_id=(problem or {}).get("id"), role="assistant", text=answer, language=language)
        return ChatResponse(answer=answer, links=[], quota=quota_payload(subscription))

    if problem is None:
        problem = repo.save_problem(
            user_id=user.id,
            vehicle_id=vehicle.get("id"),
            payload=_problem_payload(symptom=text, problem_class=problem_class, vehicle=vehicle),
        )
        context.problem = problem
    else:
        repo.save_problem(
            user_id=user.id,
            vehicle_id=vehicle.get("id"),
            problem_id=problem.get("id"),
            payload={"status": problem.get("status") or "OPEN", "symptoms": problem.get("symptoms") or [text]},
        )

    knowledge = repo.find_relevant_knowledge(vehicle=vehicle, symptom=text, limit=3)
    if knowledge:
        answer = plain_text_response(_format_internal_answer(language, knowledge[0]))
        for event in extract_technical_events(text, answer=answer):
            repo.create_vehicle_event(user_id=user.id, vehicle_id=vehicle.get("id"), problem_id=(problem or {}).get("id"), payload=event)
        repo.save_message(user_id=user.id, conversation_id=conversation_id, vehicle_id=vehicle.get("id"), problem_id=(problem or {}).get("id"), role="user", text=text, language=language)
        repo.save_message(user_id=user.id, conversation_id=conversation_id, vehicle_id=vehicle.get("id"), problem_id=(problem or {}).get("id"), role="assistant", text=answer, language=language)
        return ChatResponse(answer=answer, links=[], quota=quota_payload(subscription))

    research = await run_search_stages(
        user_id=user.id,
        vehicle_id=vehicle.get("id"),
        problem_id=(problem or {}).get("id"),
        vehicle_label=vehicle_label(vehicle),
        query=text,
        language=language,
    )
    answer = plain_text_response(_format_research_answer(language, summary=research.summary, links=research.links, sufficient=research.sufficient))
    if problem:
        repo.save_problem(
            user_id=user.id,
            vehicle_id=vehicle.get("id"),
            problem_id=problem.get("id"),
            payload={"current_conclusion": research.summary or answer, "status": "OPEN"},
        )
    for event in extract_technical_events(text, answer=answer):
        repo.create_vehicle_event(user_id=user.id, vehicle_id=vehicle.get("id"), problem_id=(problem or {}).get("id"), payload=event)
    repo.save_message(user_id=user.id, conversation_id=conversation_id, vehicle_id=vehicle.get("id"), problem_id=(problem or {}).get("id"), role="user", text=text, language=language)
    repo.save_message(user_id=user.id, conversation_id=conversation_id, vehicle_id=vehicle.get("id"), problem_id=(problem or {}).get("id"), role="assistant", text=answer, language=language)
    return ChatResponse(answer=answer, links=research.links, quota=quota_payload(research.quota or subscription))
