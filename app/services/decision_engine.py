import re

from app.schemas.chat import ChatResponse
from app.services.dialog_state_service import build_dialog_state
from app.services.formatter_service import format_from_kb, format_technical_answer
from app.services.kb_service import (
    _clean_case_answer,
    _vehicle_context_matches,
    find_latest_case_for_feedback,
    find_matching_case,
    find_matching_history_case,
    increment_case_success,
    save_knowledge_case,
)
from app.services.normalize_service import normalize_chat_input
from app.services.parser_service import ParserUnavailableError, parse_diagnostic
from app.services.puls_data_service import resolve_user_vehicle
from app.services.router_service import route_message
from app.services.user_service import get_or_create_user, update_user_after_response


_CAR_BRANDS = (
    "toyota",
    "lexus",
    "nissan",
    "infiniti",
    "honda",
    "acura",
    "mazda",
    "subaru",
    "mitsubishi",
    "suzuki",
    "bmw",
    "mercedes",
    "mercedes-benz",
    "audi",
    "volkswagen",
    "vw",
    "porsche",
    "opel",
    "skoda",
    "seat",
    "renault",
    "peugeot",
    "citroen",
    "fiat",
    "alfa romeo",
    "volvo",
    "saab",
    "land rover",
    "range rover",
    "jaguar",
    "mini",
    "ford",
    "chevrolet",
    "cadillac",
    "gmc",
    "buick",
    "dodge",
    "jeep",
    "chrysler",
    "ram",
    "tesla",
    "lincoln",
    "hyundai",
    "kia",
    "genesis",
    "lada",
    "ваз",
    "газ",
    "уаз",
    "geely",
    "chery",
    "byd",
    "haval",
    "great wall",
    "changan",
    "jac",
    "exeed",
    "omoda",
    "zeekr",
    "li auto",
    "nio",
    "xpeng",
)


def _quota_payload(user) -> dict:
    remaining = max(int(getattr(user, "requests_left", 0) or 0), 0)
    limit = 100 if remaining > 10 else 10
    return {
        "remaining": remaining,
        "used": max(limit - remaining, 0),
        "limit": limit,
        "plan_type": "paid" if limit == 100 else "free",
        "unlimited": False,
    }


def _contains_any_phrase(text: str, phrases: set[str]) -> bool:
    lowered = str(text or "").lower()
    return any(phrase in lowered for phrase in phrases if phrase)


def _normalize_phrase(text: str) -> str:
    normalized = " ".join(str(text or "").lower().split())
    normalized = re.sub(r"\b1g\s+gze\b", "1g-gze", normalized)
    normalized = re.sub(r"\bgs\s*131\b", "gs131", normalized)
    return normalized


def _extract_active_car_from_text(text: str) -> str:
    normalized = re.sub(r"[.,;!?()]+", " ", str(text or "")).strip()
    if not normalized:
        return ""

    lowered = normalized.lower()
    found_brand = ""
    for brand in _CAR_BRANDS:
        if brand in lowered:
            found_brand = brand
            break

    if not found_brand:
        return ""

    words = normalized.split()
    brand_parts = found_brand.split()
    brand_index = -1
    for index in range(len(words)):
        candidate = " ".join(words[index:index + len(brand_parts)]).lower()
        if candidate == found_brand:
            brand_index = index
            break

    if brand_index < 0:
        return ""

    car_words = words[brand_index:brand_index + 8]
    result = " ".join(car_words).strip()

    year_match = re.search(r"\b(19[8-9]\d|20[0-3]\d)\b", normalized)
    engine_match = re.search(
        r"\b(\d[.,]\d\s?(?:л|литр|liter|l)|v6|v8|v10|v12|i4|i6|tdi|tsi|tfsi|dci|hdi|cdi|"
        r"m57|n52|n54|n55|b58|m54|2gr|1gr|1zz|2zz|qr20|qr25|sr20|sr20vet|vq35|vk56|om642|"
        r"k20|k24|j35|ej20|ej25|fa20|fb25|1g[- ]?gze|1ggze|gs131)\b",
        normalized,
        re.IGNORECASE,
    )

    if year_match and year_match.group(0) not in result:
        result = f"{result} {year_match.group(0)}".strip()
    if engine_match and engine_match.group(0) not in result.lower():
        result = f"{result} {engine_match.group(0)}".strip()

    return result


def _looks_like_generic_component_query(text: str, active_car: str = "") -> bool:
    if active_car:
        return False
    lowered = _normalize_phrase(text)
    component_terms = (
        "расходомер",
        "дмрв",
        "maf",
        "map",
        "турбина",
        "дроссель",
        "форсун",
        "генератор",
        "датчик",
    )
    if not any(term in lowered for term in component_terms):
        return False
    if _extract_active_car_from_text(text):
        return False
    if re.search(r"\b(19[8-9]\d|20[0-3]\d)\b", lowered):
        return False
    if re.search(r"\b(1g-gze|1ggze|sr20vet|qr20|qr25|2gr|1gr|1zz|2zz|ej20|ej25|k20|k24)\b", lowered):
        return False
    return True


def _build_parser_history_context(history: str, *, symptom: str, active_car: str, max_blocks: int = 2) -> str:
    blocks = [block.strip() for block in str(history or "").split("\n---\n") if block.strip()]
    if not blocks:
        return ""

    needles = [_normalize_phrase(symptom), _normalize_phrase(active_car)]
    selected: list[str] = []

    for block in reversed(blocks):
        haystack = _normalize_phrase(block)
        if active_car and not _vehicle_context_matches(haystack, active_car):
            continue
        if any(needle and needle in haystack for needle in needles):
            selected.append(block)
        if len(selected) >= max_blocks:
            break

    if not selected and not active_car:
        selected = blocks[-max_blocks:]

    selected.reverse()
    return "\n---\n".join(selected)[:4000]


def _looks_like_info_followup(text: str) -> bool:
    lowered = _normalize_phrase(text)
    phrases = (
        "дай больше информации",
        "больше информации",
        "мало информации",
        "подробнее",
        "распиши подробнее",
        "подробней",
        "подробно",
        "еще информации",
        "ещё информации",
        "нужно больше",
        "хочу больше вариантов",
        "покажи глубже",
        "more information",
        "more details",
        "tell me more",
        "go deeper",
        "deeper",
    )
    return any(phrase in lowered for phrase in phrases)


def _extract_last_search_symptom(history: str) -> str:
    blocks = [block.strip() for block in str(history or "").split("\n---\n") if block.strip()]
    for block in reversed(blocks):
        message_type = ""
        symptom = ""
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if line.lower().startswith("message_type:"):
                message_type = line.split(":", 1)[1].strip().lower()
            elif line.lower().startswith("symptom:"):
                symptom = line.split(":", 1)[1].strip()
        if message_type in {"parser", "parser_fallback", "kb_match"} and symptom and not _looks_like_info_followup(symptom):
            return symptom
    return ""


def _should_use_history_for_parser(state, decision) -> bool:
    if state.is_feedback_not_helped or state.should_deep_search:
        return True
    return decision.message_type in {"followup", "followup_deep"}


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


def _should_force_parser(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    parser_triggers = (
        "как ",
        "почему",
        "настро",
        "регулиров",
        "расходомер",
        "дмрв",
        "maf",
        "не ",
        "ошиб",
        "шум",
        "стук",
        "свист",
        "дым",
        "тяг",
        "турб",
        "check",
        "obd",
        "how to",
        "replace",
        "adjust",
        "tune",
        "fix",
        "repair",
        "noise",
        "stall",
        "power",
    )
    return any(token in lowered for token in parser_triggers) or len(lowered.split()) >= 4


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


def _vehicle_label(vehicle: dict | None) -> str:
    if not vehicle:
        return ""
    parts = [
        vehicle.get("brand"),
        vehicle.get("model"),
        vehicle.get("year"),
        vehicle.get("engine"),
    ]
    return " ".join(str(part).strip() for part in parts if part).strip()


async def process_chat_message(payload: dict, source: str) -> ChatResponse:
    normalized = normalize_chat_input(payload, source=source)
    mentioned_car = _extract_active_car_from_text(normalized.text)
    if mentioned_car:
        normalized = normalized.model_copy(update={"car_info": mentioned_car})

    user = await get_or_create_user(normalized)
    resolved_vehicle = resolve_user_vehicle(
        user_id=user.id,
        car_text=mentioned_car or normalized.car_info or user.car_info,
    )
    vehicle_id = resolved_vehicle.get("id") if resolved_vehicle else None
    resolved_car_label = _vehicle_label(resolved_vehicle)
    if resolved_car_label:
        normalized = normalized.model_copy(update={"car_info": resolved_car_label})

    if user.requests_left <= 0:
        answer = "Your request limit is exhausted."
        await update_user_after_response(
            user,
            normalized,
            answer,
            should_decrease_limit=False,
            active_car=resolved_car_label or user.car_info or normalized.car_info,
            symptom=normalized.text,
            message_type="limit",
            vehicle_id=vehicle_id,
        )
        return ChatResponse(answer=answer, links=[], quota=_quota_payload(user))

    decision = await route_message(normalized, user)
    state = build_dialog_state(normalized, user, decision)
    if mentioned_car:
        state.active_car = mentioned_car
    if resolved_car_label:
        state.active_car = resolved_car_label

    generic_component_query = _looks_like_generic_component_query(normalized.text, state.active_car)

    if generic_component_query:
        state.needs_car_clarification = True
        state.needs_problem_clarification = False
        state.should_search = False
        state.should_deep_search = False

    if (
        _should_force_parser(normalized.text)
        and not generic_component_query
        and not state.is_greeting
        and not state.is_feedback_helped
        and not state.is_feedback_not_helped
    ):
        state.needs_car_clarification = False
        state.needs_problem_clarification = False
        state.should_search = True

    if _looks_like_info_followup(normalized.text) and user.conversation_history:
        state.needs_car_clarification = False
        state.needs_problem_clarification = False
        state.should_search = True
        state.should_deep_search = True
        previous_search_symptom = _extract_last_search_symptom(user.conversation_history)
        if previous_search_symptom:
            state.previous_symptom = previous_search_symptom
            state.current_symptom = previous_search_symptom

    if state.should_search and not state.should_deep_search and not state.active_car:
        state.needs_car_clarification = True
        state.needs_problem_clarification = False
        state.should_search = False

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
            vehicle_id=vehicle_id,
        )
        return ChatResponse(answer=answer_text, links=[], quota=_quota_payload(user))

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
            vehicle_id=vehicle_id,
        )
        return ChatResponse(answer=answer_text, links=[], quota=_quota_payload(user))

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
            vehicle_id=vehicle_id,
        )
        return ChatResponse(answer=answer_text, links=[], quota=_quota_payload(user))

    if state.is_feedback_helped:
        feedback_state = build_dialog_state(normalized, user, decision)
        feedback_state.current_symptom = feedback_state.previous_symptom or feedback_state.current_symptom
        matched_feedback_case = await find_latest_case_for_feedback(feedback_state)
        if matched_feedback_case is not None:
            await increment_case_success(matched_feedback_case.get("id"))

        answer_text = (
            "Отлично, рад что помогло. Я сохранил этот успешный кейс в журнал решений."
            if state.language == "ru"
            else "Great, glad it helped. I saved this successful case to the solved cases journal."
        )
        await update_user_after_response(
            user,
            normalized,
            answer_text,
            should_decrease_limit=False,
            active_car=state.active_car,
            symptom=state.previous_symptom or state.current_symptom,
            message_type="feedback_helped",
            vehicle_id=vehicle_id,
        )
        return ChatResponse(answer=answer_text, links=[], quota=_quota_payload(user))

    if state.is_feedback_not_helped:
        state.should_deep_search = True
        state.should_search = True
        previous_search_symptom = _extract_last_search_symptom(user.conversation_history)
        if previous_search_symptom:
            state.previous_symptom = previous_search_symptom
            state.current_symptom = previous_search_symptom
        elif not state.current_symptom and state.previous_symptom:
            state.current_symptom = state.previous_symptom
        if not state.active_car and user.car_info:
            state.active_car = user.car_info

    matched_case = None
    matched_case_answer = ""
    matched_case_links = []
    matched_case_is_placeholder = False
    if state.should_search and not state.should_deep_search and not _looks_like_info_followup(normalized.text):
        matched_case = await find_matching_case(state, decision)
        matched_case_answer = str((matched_case or {}).get("answer", "")).strip()
        matched_case_links = (matched_case or {}).get("links", [])
        matched_case_is_placeholder = _contains_any_phrase(
            matched_case_answer,
            {
                "please describe",
                "i need more information",
                "i need more info",
                "need more information",
            },
        )

        if (matched_case is None or not (matched_case_answer or matched_case_links) or matched_case_is_placeholder) and user.conversation_history:
            matched_case = await find_matching_history_case(
                history=user.conversation_history,
                active_car=state.active_car or normalized.car_info or user.car_info,
                symptom=state.current_symptom,
                language=state.language,
            )
            matched_case_answer = str((matched_case or {}).get("answer", "")).strip()
            matched_case_links = (matched_case or {}).get("links", [])
            matched_case_is_placeholder = _contains_any_phrase(
                matched_case_answer,
                {
                    "please describe",
                    "i need more information",
                    "i need more info",
                    "need more information",
                },
            )

        if matched_case is not None and (matched_case_answer or matched_case_links) and not matched_case_is_placeholder:
            matched_case_answer, embedded_links = _clean_case_answer(matched_case_answer)
            if embedded_links and not matched_case_links:
                matched_case_links = embedded_links
            answer_text = format_from_kb(
                language=state.language,
                answer=matched_case_answer,
                links=matched_case_links,
            )
            await update_user_after_response(
                user,
                normalized,
                answer_text,
                should_decrease_limit=False,
                active_car=state.active_car,
                symptom=state.current_symptom,
                message_type="kb_match",
                links=matched_case_links,
                vehicle_id=vehicle_id,
            )
            return ChatResponse(answer=answer_text, links=matched_case_links, quota=_quota_payload(user))

    if state.should_search:
        effective_symptom = state.previous_symptom if state.should_deep_search and state.previous_symptom else state.current_symptom
        parser_input = normalized.model_copy(update={"text": effective_symptom})
        try:
            parser_history = ""
            if _should_use_history_for_parser(state, decision):
                parser_history = _build_parser_history_context(
                    user.conversation_history or "",
                    symptom=effective_symptom,
                    active_car=state.active_car or normalized.car_info or user.car_info,
                )
            parsed_case = await parse_diagnostic(
                {
                    "active_car": state.active_car or normalized.car_info or user.car_info,
                    "symptom": effective_symptom,
                    "query": effective_symptom,
                    "conversation_history": parser_history,
                    "deep_search": bool(state.should_deep_search),
                    "language": state.language or normalized.language,
                }
            )
        except ParserUnavailableError:
            answer_text = _generic_diagnostic_fallback(
                language=state.language,
                active_car=state.active_car,
                symptom=effective_symptom,
            )
            answer_text += (
                "\n\nDid this solve the problem? If not, write 'not helped' and I will run a deeper search."
                if state.language != "ru"
                else "\n\nЭто временный ответ, потому что глубокий поиск сейчас недоступен. Если не помогло, напишите 'не помогло', и я попробую снова."
            )
            await update_user_after_response(
                user,
                normalized,
                answer_text,
                should_decrease_limit=True,
                active_car=state.active_car,
                symptom=effective_symptom,
                message_type="parser_fallback",
                links=[],
                parser_used=True,
                deep_search_used=bool(state.should_deep_search),
                vehicle_id=vehicle_id,
            )
            return ChatResponse(answer=answer_text, links=[], quota=_quota_payload(user))

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
                    "Это помогло решить проблему? Если нет - напишите 'не помогло', и я запущу более глубокий поиск."
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
                "\n\nЭто помогло решить проблему? Если нет - напишите 'не помогло', и я запущу более глубокий поиск."
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
            parser_used=True,
            deep_search_used=bool(state.should_deep_search),
            vehicle_id=vehicle_id,
            parsed_case=parsed_case,
        )
        return ChatResponse(answer=answer_text, links=response_links, quota=_quota_payload(user))

    answer_text = _fallback_diagnostic_prompt(state.language)
    await update_user_after_response(
        user,
        normalized,
        answer_text,
        should_decrease_limit=False,
        active_car=state.active_car,
        symptom=state.current_symptom,
        message_type="clarification",
        vehicle_id=vehicle_id,
    )
    return ChatResponse(answer=answer_text, links=[], quota=_quota_payload(user))
