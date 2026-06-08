from fastapi import APIRouter, HTTPException

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.dialog_state_service import build_dialog_state
from app.services.formatter_service import format_from_kb, format_technical_answer
from app.services.kb_service import find_latest_case_for_feedback, find_matching_case, increment_case_success, save_knowledge_case
from app.services.normalize_service import normalize_chat_input
from app.services.parser_service import ParserUnavailableError, parse_diagnostic
from app.services.router_service import route_message
from app.services.user_service import get_or_create_user, update_user_after_response

router = APIRouter(tags=["chat"])


def _contains_any_phrase(text: str, phrases: set[str]) -> bool:
    lowered = str(text or "").lower()
    return any(phrase in lowered for phrase in phrases if phrase)


def _greeting_text(language: str, assistant_hint: str = "") -> str:
    if assistant_hint:
        return assistant_hint
    if language == "ru":
        return "Привет! Опишите проблему с автомобилем."
    return "Hi! Describe the problem with your car."


def _clarification_text(language: str) -> str:
    if language == "ru":
        return (
            "Укажите марку, модель, год и двигатель автомобиля.\n\n"
            "Это помогло решить проблему? Если нет — напишите 'не помогло', и я запущу более глубокий поиск."
        )
    return (
        "Please provide the car make, model, year, and engine.\n\n"
        "Did this solve the problem? If not, write 'not helped' and I will run a deeper search."
    )


def _fallback_diagnostic_prompt(language: str) -> str:
    if language == "ru":
        return "Опишите проблему с автомобилем, и я начну диагностику."
    return "Describe the problem with the car and I’ll start the diagnosis."


def _generic_diagnostic_fallback(*, language: str, active_car: str, symptom: str) -> str:
    if language == "ru":
        parts = [
            "Похоже на потерю тяги после прогрева.",
            "Сначала проверьте расход воздуха (ДМРВ/MAF), подсос воздуха, давление топлива и датчик температуры ОЖ.",
            "Если есть турбина, проверьте управление наддувом и патрубки.",
            "Если есть коды ошибок OBD, пришлите их — это сильно сузит поиск.",
        ]
        if active_car:
            parts.insert(1, f"Машина: {active_car}.")
        if symptom:
            parts.insert(1, f"Симптом: {symptom}.")
        return "\n\n".join(parts)
    return (
        "This looks like a warm-engine loss of power issue.\n\n"
        "First check airflow (MAF), air leaks, fuel pressure, coolant temperature sensor, and boost control if the car has a turbo.\n\n"
        "If you have OBD codes, send them and I’ll narrow it down."
    )


async def handle_message(payload: dict, source: str) -> ChatResponse:
    normalized = normalize_chat_input(payload, source=source)
    user = await get_or_create_user(normalized)

    if user.requests_left <= 0:
        answer = "Your request limit is exhausted."
        await update_user_after_response(
            user,
            normalized,
            answer,
            should_decrease_limit=False,
            active_car=user.car_info or normalized.car_info,
            symptom=normalized.text,
            message_type="limit",
        )
        return ChatResponse(answer=answer, links=[])

    decision = await route_message(normalized, user)
    state = build_dialog_state(normalized, user, decision)

    if state.is_greeting:
        answer_text = _greeting_text(state.language, decision.response)
        await update_user_after_response(
            user,
            normalized,
            answer_text,
            should_decrease_limit=False,
            active_car=state.active_car,
            symptom=state.current_symptom,
            message_type="greeting",
        )
        return ChatResponse(answer=answer_text, links=[])

    if state.needs_car_clarification:
        answer_text = _clarification_text(state.language)
        await update_user_after_response(
            user,
            normalized,
            answer_text,
            should_decrease_limit=False,
            active_car=state.active_car,
            symptom=state.current_symptom,
            message_type="clarification",
        )
        return ChatResponse(answer=answer_text, links=[])

    if state.needs_problem_clarification:
        answer_text = _fallback_diagnostic_prompt(state.language)
        await update_user_after_response(
            user,
            normalized,
            answer_text,
            should_decrease_limit=False,
            active_car=state.active_car,
            symptom=state.current_symptom,
            message_type="clarification",
        )
        return ChatResponse(answer=answer_text, links=[])

    if state.is_feedback_helped:
        feedback_state = build_dialog_state(normalized, user, decision)
        feedback_state.current_symptom = feedback_state.previous_symptom or feedback_state.current_symptom
        matched_feedback_case = await find_latest_case_for_feedback(feedback_state)
        if matched_feedback_case is not None:
            await increment_case_success(matched_feedback_case.get("id"))

        answer_text = (
            "Отлично, рад что помогло. Если появится новая проблема, опишите её."
            if state.language == "ru"
            else "Great, glad it helped. If a new issue appears, describe it and I’ll take a look."
        )
        await update_user_after_response(
            user,
            normalized,
            answer_text,
            should_decrease_limit=False,
            active_car=state.active_car,
            symptom=state.previous_symptom or state.current_symptom,
            message_type="feedback_helped",
        )
        return ChatResponse(answer=answer_text, links=[])

    if state.is_feedback_not_helped:
        state.should_deep_search = True
        state.should_search = True
        if not state.current_symptom and state.previous_symptom:
            state.current_symptom = state.previous_symptom
        if not state.active_car and user.car_info:
            state.active_car = user.car_info

    matched_case = None
    matched_case_answer = ""
    matched_case_links = []
    matched_case_is_placeholder = False
    if state.should_search and not state.should_deep_search:
        matched_case = await find_matching_case(state, decision)
        matched_case_answer = str((matched_case or {}).get("answer", "")).strip()
        matched_case_links = (matched_case or {}).get("links", [])
        matched_case_is_placeholder = _contains_any_phrase(
            matched_case_answer,
            {
                "?????????????????????? ???? ??????????????",
                "?????? ????????????",
                "?? ?????????? ????????????, ???? ?????? ???? ?????????????? ????????????????????",
                "?????? ???? ?????????????? ????????????????????",
                "???? ???????? ???????????????? ????????????????",
                "???? ???????? ???????????????? ????????????????",
                "?????????????? ????????????????",
                "please describe",
                "i need more information",
                "i need more info",
                "need more information",
            },
        )
        if matched_case is not None and (matched_case_answer or matched_case_links) and not matched_case_is_placeholder:
            answer_text = format_from_kb(
                language=state.language,
                answer=matched_case_answer,
                links=matched_case_links,
            )
            await update_user_after_response(
                user,
                normalized,
                answer_text,
                should_decrease_limit=bool(state.should_search),
                active_car=state.active_car,
                symptom=state.current_symptom,
                message_type="kb_match",
            )
            return ChatResponse(answer=answer_text, links=matched_case_links)

    if state.should_search:
        effective_symptom = state.previous_symptom if state.should_deep_search and state.previous_symptom else state.current_symptom
        parser_input = normalized.model_copy(update={"text": effective_symptom})
        try:
            parsed_case = await parse_diagnostic(
                {
                    "active_car": state.active_car or normalized.car_info or user.car_info,
                    "symptom": effective_symptom,
                    "query": effective_symptom,
                    "conversation_history": user.conversation_history or "",
                    "deep_search": bool(state.should_deep_search),
                    "language": state.language or normalized.language,
                }
            )
        except ParserUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        await save_knowledge_case(parser_input, decision, parsed_case)

        diagnosis_text = parsed_case.get("parser_summary") or ""
        extracted_cases = parsed_case.get("extracted_cases") or []
        probable_causes = [case.get("cause", "") for case in extracted_cases if case.get("cause")]
        first_checks = [case.get("solution", "") for case in extracted_cases if case.get("solution")]
        less_likely: list[str] = []
        if len(probable_causes) > 2:
            less_likely = probable_causes[2:]
            probable_causes = probable_causes[:2]
        response_links = parsed_case.get("links") or []
        parser_placeholder = _contains_any_phrase(
            diagnosis_text,
            {
                "диагностика не найдена",
                "нет данных",
                "я готов помочь, но мне не хватает информации",
                "мне не хватает информации",
                "diagnosis not found",
                "no data",
                "need more information",
                "i need more info",
            },
        )

        if diagnosis_text and not parser_placeholder:
            answer_text = format_technical_answer(
                language=state.language,
                diagnosis=diagnosis_text or (probable_causes[0] if probable_causes else ""),
                probable_causes=probable_causes,
                first_checks=first_checks[:3],
                less_likely=less_likely,
                links=response_links,
                question_tail=(
                    "??? ??????? ?????? ????????? ???? ??? ? ???????? '?? ???????', ? ? ?????? ????? ???????? ?????."
                    if state.language == "ru"
                    else "Did this solve the problem? If not, write 'not helped' and I will run a deeper search."
                ),
            )
        else:
            answer_text = _generic_diagnostic_fallback(
                language=state.language,
                active_car=state.active_car,
                symptom=effective_symptom,
            )
            answer_text += (
                "\n\n??? ??????? ?????? ????????? ???? ??? ? ???????? '?? ???????', ? ? ?????? ????? ???????? ?????."
                if state.language == "ru"
                else "\n\nDid this solve the problem? If not, write 'not helped' and I will run a deeper search."
            )
        await update_user_after_response(
            user,
            normalized,
            answer_text,
            should_decrease_limit=True,
            active_car=state.active_car,
            symptom=effective_symptom,
            message_type="parser",
            links=response_links,
        )
        return ChatResponse(answer=answer_text, links=response_links)

    answer_text = _fallback_diagnostic_prompt(state.language)
    await update_user_after_response(
        user,
        normalized,
        answer_text,
        should_decrease_limit=False,
        active_car=state.active_car,
        symptom=state.current_symptom,
        message_type="clarification",
    )
    return ChatResponse(answer=answer_text, links=[])


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    return await handle_message(payload.model_dump(), source="web")
