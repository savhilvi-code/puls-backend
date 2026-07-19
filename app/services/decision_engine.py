import re

from app.schemas.chat import ChatResponse
from app.services.conversation_service import get_latest_conversation_context
from app.services.dialog_state_service import build_dialog_state
from app.services.formatter_service import format_from_kb, format_technical_answer
from app.services.kb_service import (
    _clean_case_answer,
    _vehicle_context_matches,
    find_latest_case_for_feedback,
    find_matching_case,
    find_matching_history_case,
    increment_case_success,
)
from app.services.normalize_service import normalize_chat_input
from app.services.openai_service import translate_segments
from app.services.parser_service import ParserUnavailableError, parse_diagnostic
from app.services.puls_data_service import resolve_user_vehicle
from app.services.router_service import route_message
from app.services.subscription_service import can_run_parser, ensure_user_subscription, quota_payload
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
    if getattr(user, "id", None):
        return quota_payload(ensure_user_subscription(user_id=user.id))
    remaining = max(int(getattr(user, "requests_left", 0) or 0), 0)
    return {
        "remaining": remaining,
        "used": max(10 - remaining, 0),
        "limit": 10,
        "plan_type": "free",
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


def _resolve_dialog_vehicle_binding(*, user_id: int | None, car_text: str) -> tuple[int | None, str]:
    if user_id is None or not str(car_text or "").strip():
        return None, ""
    dialog_vehicle = resolve_user_vehicle(
        user_id=user_id,
        car_text=car_text,
    )
    dialog_vehicle_label = _vehicle_label(dialog_vehicle)
    dialog_vehicle_id = dialog_vehicle.get("id") if dialog_vehicle else None
    return dialog_vehicle_id, dialog_vehicle_label


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


def _looks_like_service_advice_query(text: str) -> bool:
    lowered = _normalize_phrase(text)
    service_terms = (
        "какое масло",
        "какое масло подходит",
        "какое масло лить",
        "какое масло залить",
        "какую жидкость",
        "какую охлаждающую жидкость",
        "какой антифриз",
        "какой atf",
        "какое трансмиссионное масло",
        "какую вязкость",
        "какой допуск масла",
        "what oil",
        "which oil",
        "oil recommendation",
        "oil spec",
        "oil viscosity",
        "coolant",
        "antifreeze",
        "transmission fluid",
        "atf",
        "brake fluid",
        "power steering fluid",
    )
    problem_terms = (
        "не работает",
        "не завод",
        "плохо",
        "стучит",
        "свист",
        "дым",
        "ошибк",
        "теряет тягу",
        "loss of power",
        "stall",
        "noise",
        "turbo",
    )
    return any(term in lowered for term in service_terms) and not any(term in lowered for term in problem_terms)


def _service_advice_clarification(*, language: str, active_car: str) -> str:
    if language == "ru":
        if active_car:
            return (
                f"Уточните, пожалуйста, для какого узла на {active_car} нужно подобрать жидкость: "
                "двигатель, АКПП/вариатор, раздатка, редуктор, ГУР или тормозная система. "
                "Если знаете, напишите желаемую вязкость или допуск из мануала."
            )
        return (
            "Уточните, пожалуйста, для какого узла нужно подобрать жидкость: "
            "двигатель, АКПП/вариатор, раздатка, редуктор, ГУР или тормозная система. "
            "И напишите марку, модель, год и двигатель автомобиля."
        )
    if active_car:
        return (
            f"Please specify which system on your {active_car} needs fluid selection: "
            "engine, automatic transmission/CVT, transfer case, differential, power steering, or brakes. "
            "If you know it, include the target viscosity or OEM specification."
        )
    return (
        "Please specify which system needs fluid selection: engine, automatic transmission/CVT, "
        "transfer case, differential, power steering, or brakes. Also include the car make, model, year, and engine."
    )


def _extract_service_target_reply(text: str) -> str:
    lowered = _normalize_phrase(text)
    target_map = {
        "engine": ("для двс", "двс", "двигатель", "для двигателя", "в двигатель", "engine", "motor"),
        "transmission": (
            "акпп",
            "вариатор",
            "cvt",
            "atf",
            "коробка",
            "трансмиссия",
            "автомат",
            "автоматическая",
            "гидромеханическая",
            "automatic",
            "gearbox",
            "transmission",
        ),
        "transfer_case": ("раздатка", "transfer case"),
        "differential": ("редуктор", "дифф", "differential"),
        "power_steering": ("гур", "power steering", "steering fluid"),
        "brakes": ("тормоз", "brake fluid", "brakes"),
    }
    for target, phrases in target_map.items():
        if any(phrase in lowered for phrase in phrases):
            return target
    return ""


def _looks_like_service_clarification_prompt(text: str) -> bool:
    lowered = _normalize_phrase(text)
    return (
        "для какого узла" in lowered
        or "which system" in lowered
        or "needs fluid selection" in lowered
        or "нужно подобрать жидкость" in lowered
    )


def _extract_service_target_from_prompt(text: str) -> str:
    lowered = _normalize_phrase(text)
    prompt_map = {
        "engine": ("речь про двигатель", "this is for the engine"),
        "transmission": ("речь про акпп/вариатор", "automatic transmission/cvt", "which gearbox is installed"),
        "transfer_case": ("речь про раздатку", "this is for the transfer case"),
        "differential": ("речь про редуктор", "this is for the differential"),
        "power_steering": ("речь про гур", "power steering system"),
        "brakes": ("речь про тормозную систему", "brake system"),
    }
    for target, phrases in prompt_map.items():
        if any(phrase in lowered for phrase in phrases):
            return target
    return ""


def _extract_service_transmission_kind(text: str) -> str:
    lowered = _normalize_phrase(text)
    if any(phrase in lowered for phrase in ("вариатор", "cvt")):
        return "cvt"
    if any(
        phrase in lowered
        for phrase in (
            "обычный автомат",
            "обычный atf",
            "обычный автоматический",
            "гидромеханический",
            "автомат",
            "automatic",
            "regular atf",
            "normal atf",
        )
    ):
        return "automatic"
    return ""


def _extract_service_subtype(text: str, target: str = "") -> str:
    lowered = _normalize_phrase(text)
    if any(token in lowered for token in ("cvt", "вариатор")):
        return "cvt"
    if any(token in lowered for token in ("atf", "обычный автомат", "automatic", "normal atf", "regular atf")):
        return "atf"
    if any(token in lowered for token in ("dot 3", "dot 4", "dot 5", "dot")):
        return "dot"
    if any(token in lowered for token in ("антифриз", "coolant", "охлажда")):
        return "coolant"
    if re.search(r"\b\d{1,2}w-\d{2}\b", lowered, re.IGNORECASE) or any(
        token in lowered for token in ("вязкость", "viscosity", "oil spec", "допуск масла")
    ):
        return "viscosity"
    if target == "power_steering" or any(token in lowered for token in ("гур", "power steering", "steering fluid")):
        return "steering"
    if any(token in lowered for token in ("климат", "climate")):
        return "climate"
    return ""


def _looks_like_service_followup_reply(text: str) -> bool:
    lowered = _normalize_phrase(text)
    if not lowered:
        return False
    if _extract_active_car_from_text(text):
        return True
    if _extract_service_target_reply(text) or _extract_service_transmission_kind(text) or _extract_service_subtype(text):
        return True
    if any(
        token in lowered
        for token in (
            "dot",
            "oem",
            "мануал",
            "gearbox",
            "короб",
            "допуск",
            "вязкость",
            "climate",
            "климат",
            "lsd",
            "hydraulic",
            "гидравл",
        )
    ):
        return True
    return len(lowered.split()) <= 8 and not _looks_like_diagnostic_intent(text)


def _is_service_flow_active(*, service_seed_query: str, latest_assistant_text: str, latest_user_text: str, current_text: str) -> bool:
    if not service_seed_query:
        return False
    if _looks_like_service_advice_query(current_text):
        return True
    if _looks_like_service_clarification_prompt(latest_assistant_text) or _looks_like_service_detail_prompt(latest_assistant_text):
        return _looks_like_service_followup_reply(current_text)
    return _looks_like_service_advice_query(latest_user_text) and _looks_like_service_followup_reply(current_text)


def _service_target_followup_response(*, language: str, active_car: str, target: str) -> str:
    car_part = f" на {active_car}" if active_car else ""
    if language == "ru":
        replies = {
            "engine": (
                f"Понял, речь про двигатель{car_part}. Напишите климат эксплуатации и желаемую вязкость, "
                "если уже смотрели мануал. Если допуска не знаете, я подскажу, на что ориентироваться по вязкости и спецификации."
            ),
            "transmission": (
                f"Понял, речь про АКПП/вариатор{car_part}. Уточните, пожалуйста, какая именно коробка стоит на машине "
                "и нужен ли обычный ATF или жидкость для вариатора."
            ),
            "transfer_case": f"Понял, речь про раздатку{car_part}. Уточните, пожалуйста, тип привода и если знаете требуемый допуск масла.",
            "differential": f"Понял, речь про редуктор{car_part}. Уточните, передний или задний редуктор и есть ли требования по LSD/обычному дифференциалу.",
            "power_steering": f"Понял, речь про ГУР{car_part}. Уточните, нужен именно гидравлический ГУР или электроусилитель, чтобы не спутать тип жидкости.",
            "brakes": f"Понял, речь про тормозную систему{car_part}. Уточните, нужен подбор тормозной жидкости DOT и есть ли требования из мануала.",
        }
        return replies.get(
            target,
            f"Понял, нужен подбор жидкости{car_part}. Уточните, пожалуйста, нужный узел и желаемый допуск или вязкость."
        )
    replies = {
        "engine": (
            f"Understood, this is for the engine{car_part}. Please tell me the climate and preferred viscosity "
            "if you already checked the manual. If you do not know the spec yet, I can guide you by viscosity and approval."
        ),
        "transmission": (
            f"Understood, this is for the automatic transmission/CVT{car_part}. Please clarify which gearbox is installed "
            "and whether you need regular ATF or a dedicated CVT fluid."
        ),
        "transfer_case": f"Understood, this is for the transfer case{car_part}. Please clarify the drivetrain type and any oil approval if you know it.",
        "differential": f"Understood, this is for the differential{car_part}. Please clarify whether it is the front or rear differential and whether LSD requirements apply.",
        "power_steering": f"Understood, this is for the power steering system{car_part}. Please confirm whether it is hydraulic power steering so I do not mix it with EPS.",
        "brakes": f"Understood, this is for the brake system{car_part}. Please confirm whether you need brake fluid selection and any DOT requirement from the manual.",
    }
    return replies.get(
        target,
        f"Understood, you need fluid selection{car_part}. Please clarify the exact system and any viscosity or approval you want to match."
    )


def _looks_like_service_detail_prompt(text: str) -> bool:
    lowered = _normalize_phrase(text)
    return any(
        phrase in lowered
        for phrase in (
            "\u043a\u043b\u0438\u043c\u0430\u0442 \u044d\u043a\u0441\u043f\u043b\u0443\u0430\u0442\u0430\u0446\u0438\u0438",
            "\u0436\u0435\u043b\u0430\u0435\u043c\u0443\u044e \u0432\u044f\u0437\u043a\u043e\u0441\u0442\u044c",
            "\u0435\u0441\u043b\u0438 \u0443\u0436\u0435 \u0441\u043c\u043e\u0442\u0440\u0435\u043b\u0438 \u043c\u0430\u043d\u0443\u0430\u043b",
            "\u043a\u0430\u043a\u0430\u044f \u0438\u043c\u0435\u043d\u043d\u043e \u043a\u043e\u0440\u043e\u0431\u043a\u0430",
            "\u0442\u0438\u043f \u043f\u0440\u0438\u0432\u043e\u0434\u0430",
            "\u043f\u0435\u0440\u0435\u0434\u043d\u0438\u0439 \u0438\u043b\u0438 \u0437\u0430\u0434\u043d\u0438\u0439 \u0440\u0435\u0434\u0443\u043a\u0442\u043e\u0440",
            "\u043d\u0443\u0436\u0435\u043d \u0438\u043c\u0435\u043d\u043d\u043e \u0433\u0438\u0434\u0440\u0430\u0432\u043b\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u0433\u0443\u0440",
            "\u043d\u0443\u0436\u0435\u043d \u043f\u043e\u0434\u0431\u043e\u0440 \u0442\u043e\u0440\u043c\u043e\u0437\u043d\u043e\u0439 \u0436\u0438\u0434\u043a\u043e\u0441\u0442\u0438",
            "preferred viscosity",
            "checked the manual",
            "which gearbox is installed",
            "drivetrain type",
            "front or rear differential",
            "hydraulic power steering",
            "brake fluid selection",
        )
    )


def _looks_like_vehicle_correction_feedback(text: str) -> bool:
    lowered = _normalize_phrase(text)
    if not lowered:
        return False
    explicit_markers = (
        "я спросил про",
        "я спрашивал про",
        "нет я спросил про",
        "нет, я спросил про",
        "не про ниссан",
        "не x trail",
        "не x-trail",
        "not nissan",
        "i asked about",
        "i asked for",
        "wrong car",
        "about crown",
    )
    if any(marker in lowered for marker in explicit_markers):
        return True
    return "про краун" in lowered or "about crown" in lowered


def _build_service_parser_query(
    *,
    language: str,
    seed_query: str,
    assistant_prompt: str,
    user_reply: str,
    service_target: str,
) -> str:
    prompt_text = str(assistant_prompt or "")
    reply_text = str(user_reply or "").strip()
    base_query = str(seed_query or "").strip()
    if not reply_text:
        return base_query

    transmission_kind = _extract_service_transmission_kind(reply_text)

    if language == "ru":
        if service_target == "transmission":
            if transmission_kind == "automatic":
                return (
                    f"{base_query}. Уточнение пользователя: речь про АКПП, обычный автомат, нужен обычный ATF, не вариатор. "
                    f"Дополнительные условия пользователя: {reply_text}."
                )
            if transmission_kind == "cvt":
                return (
                    f"{base_query}. Уточнение пользователя: речь про вариатор, нужна жидкость CVT, не обычный ATF. "
                    f"Дополнительные условия пользователя: {reply_text}."
                )
            return (
                f"{base_query}. Уточнение пользователя: речь про АКПП/трансмиссию. "
                f"Дополнительные условия пользователя: {reply_text}."
            )
        if service_target == "engine" and "климат эксплуатации" in _normalize_phrase(prompt_text):
            return f"{base_query}. Условия эксплуатации пользователя: {reply_text}."
        return f"{base_query}. Дополнительные условия пользователя: {reply_text}."

    if service_target == "transmission":
        if transmission_kind == "automatic":
            return (
                f"{base_query}. User clarification: this is for a regular automatic transmission, regular ATF, not a CVT. "
                f"Additional user details: {reply_text}."
            )
        if transmission_kind == "cvt":
            return (
                f"{base_query}. User clarification: this is for a CVT and requires CVT fluid, not regular ATF. "
                f"Additional user details: {reply_text}."
            )
        return f"{base_query}. User clarification: this is for the transmission. Additional user details: {reply_text}."
    if service_target == "engine" and "climate" in _normalize_phrase(prompt_text):
        return f"{base_query}. User operating climate: {reply_text}."
    return f"{base_query}. Additional user details: {reply_text}."


def _prepend_service_brief(*, answer_text: str, language: str, active_car: str, symptom: str, service_target: str = "") -> str:
    text = str(answer_text or "").strip()
    if not text:
        return text
    lowered = text.lower()
    if lowered.startswith("коротко:") or lowered.startswith("briefly:"):
        return text

    viscosity_match = re.search(r"\b\d{1,2}w-\d{2}\b", text, re.IGNORECASE)
    volume_match = re.search(r"\b\d+(?:[.,]\d+)?\s*л\b", text, re.IGNORECASE)

    if not _looks_like_service_advice_query(symptom):
        return text

    if language == "ru":
        car_phrase = f" для {active_car}" if active_car else ""
        if service_target == "transmission":
            if any(term in lowered for term in ("вариатор", "cvt")):
                brief = f"Коротко: в АКПП/вариатор{car_phrase} нужна жидкость CVT по заводскому допуску."
            else:
                brief = f"Коротко: в АКПП{car_phrase} нужен обычный ATF по заводскому допуску."
        elif service_target == "brakes":
            brief = f"Коротко: в тормозную систему{car_phrase} нужна тормозная жидкость нужного DOT по заводскому допуску."
        elif service_target == "engine":
            oil_phrase = viscosity_match.group(0).upper() if viscosity_match else "подходящую вязкость по мануалу"
            volume_phrase = f", объем примерно {volume_match.group(0)}" if volume_match else ""
            brief = f"Коротко: в двигатель{car_phrase} лучше заливать синтетическое масло {oil_phrase}{volume_phrase}."
        else:
            brief = f"Коротко: для подбора жидкости{car_phrase} ориентируйтесь на заводской допуск и тип узла."
    else:
        car_phrase = f" for {active_car}" if active_car else ""
        if service_target == "transmission":
            if any(term in lowered for term in ("вариатор", "cvt")):
                brief = f"Briefly: the transmission{car_phrase} needs OEM-spec CVT fluid."
            else:
                brief = f"Briefly: the automatic transmission{car_phrase} needs OEM-spec regular ATF."
        elif service_target == "brakes":
            brief = f"Briefly: the brake system{car_phrase} needs the OEM-recommended DOT brake fluid."
        elif service_target == "engine":
            oil_phrase = viscosity_match.group(0).upper() if viscosity_match else "the OEM-recommended viscosity"
            volume_phrase = f", roughly {volume_match.group(0)}" if volume_match else ""
            brief = f"Briefly: use a full-synthetic engine oil in {oil_phrase}{volume_phrase}{car_phrase}."
        else:
            brief = f"Briefly: match the fluid to the exact system{car_phrase} and OEM approval."

    return f"{brief}\n\n{text}"


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


def _generic_diagnostic_fallback(*, language: str, active_car: str, symptom: str, service_target: str = "") -> str:
    if _looks_like_service_advice_query(symptom):
        if language == "ru":
            car_phrase = f" для {active_car}" if active_car else ""
            if service_target == "transmission":
                return (
                    f"Для точного подбора жидкости в АКПП{car_phrase} нужно знать точное обозначение коробки и заводской допуск ATF.\n\n"
                      "Если под рукой нет мануала, пришлите код коробки, шильдик трансмиссии или рынок/год выпуска машины."
                  )
            if service_target == "brakes":
                return (
                    f"Для точного подбора тормозной жидкости{car_phrase} нужно знать требование по DOT и желательно заводской допуск.\n\n"
                    "Если мануала нет, обычно ориентируются на тип DOT, год машины и состояние тормозной системы. Пришлите рынок/год выпуска и, если знаете, предыдущую жидкость."
                )
            if service_target == "engine":
                return (
                    f"Для точного подбора моторного масла{car_phrase} нужно знать заводской допуск, климат и желаемый интервал замены.\n\n"
                    "Если мануала нет, я подберу безопасный диапазон по вязкости и спецификациям."
                )
            return (
                f"Для точного подбора жидкости{car_phrase} нужно знать конкретный узел и заводской допуск.\n\n"
                "Если мануала нет, пришлите больше данных по машине и типу агрегата."
            )
        car_phrase = f" for {active_car}" if active_car else ""
        if service_target == "transmission":
            return (
                f"To choose the correct transmission fluid{car_phrase}, I need the exact gearbox designation and OEM ATF approval.\n\n"
                "If you do not have the manual, send the gearbox code, transmission tag, or the market/year of the car."
            )
        if service_target == "brakes":
            return (
                f"To choose the correct brake fluid{car_phrase}, I need the DOT requirement and ideally the OEM approval.\n\n"
                "If you do not have the manual, send the market/year of the car and any previous brake fluid spec you know."
            )
        if service_target == "engine":
            return (
                f"To choose the correct engine oil{car_phrase}, I need the OEM approval, climate, and service interval.\n\n"
                "If you do not have the manual, I can still narrow it down to a safe viscosity/specification range."
            )
        return (
            f"To choose the correct fluid{car_phrase}, I need the exact system and OEM approval.\n\n"
            "If you do not have the manual, send more details about the car and the assembly."
        )

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


async def _localize_links(links: list[dict], language: str) -> list[dict]:
    if not links:
        return []

    titles = [str(item.get("title") or "") for item in links]
    descriptions = [str(item.get("description") or "") for item in links]
    localized_titles = await translate_segments(segments=titles, target_language=language)
    localized_descriptions = await translate_segments(segments=descriptions, target_language=language)

    localized_links: list[dict] = []
    for index, item in enumerate(links):
        localized = dict(item)
        localized["title"] = localized_titles[index] if index < len(localized_titles) else localized.get("title", "")
        localized["description"] = localized_descriptions[index] if index < len(localized_descriptions) else localized.get("description", "")
        localized_links.append(localized)
    return localized_links


async def _localize_text_blocks(blocks: list[str], language: str) -> list[str]:
    return await translate_segments(segments=blocks, target_language=language)


def _should_clear_vehicle_binding(*, active_car: str, resolved_car_label: str, mentioned_car: str, state) -> bool:
    if not active_car:
        return False
    if mentioned_car:
        return True
    if getattr(state, "is_feedback_helped", False) or getattr(state, "is_feedback_not_helped", False):
        return True
    if getattr(state, "should_deep_search", False) or getattr(state, "message_type", "") in {"followup", "followup_deep"}:
        return True
    if resolved_car_label and not _vehicle_context_matches(resolved_car_label, active_car):
        return True
    return False


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

    decision = await route_message(normalized, user)
    state = build_dialog_state(normalized, user, decision)
    latest_context = get_latest_conversation_context(user_id=user.id)
    service_seed_query = str(latest_context.get("latest_service_query") or "").strip()
    service_seed_car = _extract_active_car_from_text(service_seed_query)
    latest_assistant_text = str(latest_context.get("last_assistant_text") or "")
    latest_user_text = str(latest_context.get("last_user_text") or "")
    service_prompt_target = _extract_service_target_from_prompt(latest_assistant_text)
    service_reply_target = _extract_service_target_reply(normalized.text)
    service_target = service_prompt_target or service_reply_target
    if not (
        _looks_like_service_clarification_prompt(latest_assistant_text)
        or _looks_like_service_detail_prompt(latest_assistant_text)
    ):
        service_target = (
            service_target
            or _extract_service_target_reply(latest_user_text)
            or _extract_service_target_reply(service_seed_query)
        )
    service_flow_active = _is_service_flow_active(
        service_seed_query=service_seed_query,
        latest_assistant_text=latest_assistant_text,
        latest_user_text=latest_user_text,
        current_text=normalized.text,
    )
    service_subtype = _extract_service_subtype(normalized.text, service_target)
    if not service_subtype:
        service_subtype = _extract_service_subtype(service_seed_query, service_target)
    state.active_service_flow = service_flow_active
    state.service_target = service_target
    state.service_subtype = service_subtype
    if mentioned_car:
        state.active_car = mentioned_car
    elif resolved_car_label and (not state.active_car or _vehicle_context_matches(state.active_car, resolved_car_label)):
        state.active_car = resolved_car_label
    elif service_flow_active:
        remembered_car = (
            service_seed_car
            or str(latest_context.get("active_car") or "").strip()
            or state.active_car
        )
        if remembered_car:
            state.active_car = remembered_car

    if state.active_car and _should_clear_vehicle_binding(
        active_car=state.active_car,
        resolved_car_label=resolved_car_label,
        mentioned_car=mentioned_car,
        state=state,
    ):
        dialog_vehicle = resolve_user_vehicle(
            user_id=user.id,
            car_text=state.active_car,
        )
        dialog_vehicle_label = _vehicle_label(dialog_vehicle)
        if dialog_vehicle and dialog_vehicle_label:
            vehicle_id = dialog_vehicle.get("id")
            normalized = normalized.model_copy(update={"car_info": dialog_vehicle_label})
            state.active_car = dialog_vehicle_label
        elif not dialog_vehicle_label:
            vehicle_id = None

    generic_component_query = _looks_like_generic_component_query(normalized.text, state.active_car)

    if generic_component_query:
        state.needs_car_clarification = True
        state.needs_problem_clarification = False
        state.should_search = False
        state.should_deep_search = False

    if service_flow_active:
        state.needs_car_clarification = False
        state.needs_problem_clarification = False

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
            force_new_conversation=bool(mentioned_car),
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
            force_new_conversation=bool(mentioned_car),
        )
        return ChatResponse(answer=answer_text, links=[], quota=_quota_payload(user))

    service_target_reply = _extract_service_target_reply(normalized.text)
    if (
        service_target_reply
        and latest_context
        and _looks_like_service_advice_query(latest_user_text)
        and _looks_like_service_clarification_prompt(latest_assistant_text)
        and not state.is_feedback_helped
        and not state.is_feedback_not_helped
    ):
        effective_car = (
            service_seed_car
            or state.active_car
            or str(latest_context.get("active_car") or "").strip()
            or normalized.car_info
            or user.car_info
        )
        if effective_car:
            state.active_car = effective_car
        answer_text = _service_target_followup_response(
            language=state.language,
            active_car=effective_car,
            target=service_target_reply,
        )
        await update_user_after_response(
            user,
            normalized,
            answer_text,
            should_decrease_limit=False,
            active_car=effective_car,
            symptom=str(latest_user_text or state.current_symptom),
            message_type="clarification",
            vehicle_id=vehicle_id,
            force_new_conversation=bool(mentioned_car),
        )
        return ChatResponse(answer=answer_text, links=[], quota=_quota_payload(user))

    if (
        service_reply_target
        and _looks_like_service_advice_query(normalized.text)
        and not _looks_like_service_clarification_prompt(latest_assistant_text)
        and not _looks_like_service_detail_prompt(latest_assistant_text)
        and not state.is_feedback_helped
        and not state.is_feedback_not_helped
    ):
        answer_text = _service_target_followup_response(
            language=state.language,
            active_car=state.active_car,
            target=service_reply_target,
        )
        await update_user_after_response(
            user,
            normalized,
            answer_text,
            should_decrease_limit=False,
            active_car=state.active_car,
            symptom=normalized.text,
            message_type="clarification",
            vehicle_id=vehicle_id,
            force_new_conversation=bool(mentioned_car),
        )
        return ChatResponse(answer=answer_text, links=[], quota=_quota_payload(user))

    if _looks_like_service_advice_query(normalized.text) and not state.is_feedback_helped and not state.is_feedback_not_helped:
        answer_text = _service_advice_clarification(
            language=state.language,
            active_car=state.active_car,
        )
        await update_user_after_response(
            user,
            normalized,
            answer_text,
            should_decrease_limit=False,
            active_car=state.active_car,
            symptom=state.current_symptom,
            message_type="clarification",
            vehicle_id=vehicle_id,
            force_new_conversation=bool(mentioned_car),
        )
        return ChatResponse(answer=answer_text, links=[], quota=_quota_payload(user))

    service_detail_context = bool(
        service_seed_query
        and _looks_like_service_detail_prompt(latest_assistant_text)
        and not state.is_feedback_helped
        and not state.is_feedback_not_helped
    )
    if service_detail_context and not _looks_like_service_advice_query(normalized.text):
        state.needs_car_clarification = False
        state.needs_problem_clarification = False
        state.should_search = True
        state.current_symptom = service_seed_query
        if service_seed_car:
            state.active_car = service_seed_car
            dialog_vehicle_id, dialog_vehicle_label = _resolve_dialog_vehicle_binding(
                user_id=user.id,
                car_text=service_seed_car,
            )
            if dialog_vehicle_label:
                vehicle_id = dialog_vehicle_id
                normalized = normalized.model_copy(update={"car_info": dialog_vehicle_label})
                state.active_car = dialog_vehicle_label
            else:
                vehicle_id = None

    vehicle_correction_feedback = bool(
        service_seed_query
        and state.is_feedback_not_helped
        and _looks_like_vehicle_correction_feedback(normalized.text)
    )
    if vehicle_correction_feedback:
        corrected_car = service_seed_car or mentioned_car or state.active_car
        if corrected_car:
            state.active_car = corrected_car
        answer_text = _service_target_followup_response(
            language=state.language,
            active_car=state.active_car,
            target=service_prompt_target or _extract_service_target_reply(service_seed_query) or "engine",
        )
        await update_user_after_response(
            user,
            normalized,
            answer_text,
            should_decrease_limit=False,
            active_car=state.active_car,
            symptom=service_seed_query,
            message_type="clarification",
            vehicle_id=vehicle_id,
            force_new_conversation=False,
        )
        return ChatResponse(answer=answer_text, links=[], quota=_quota_payload(user))
    elif not state.active_car:
        state.active_car = str(latest_context.get("active_car") or "").strip()

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
            force_new_conversation=bool(mentioned_car),
        )
        return ChatResponse(answer=answer_text, links=[], quota=_quota_payload(user))

    if state.is_feedback_helped:
        feedback_state = build_dialog_state(normalized, user, decision)
        feedback_state.current_symptom = feedback_state.previous_symptom or feedback_state.current_symptom
        matched_feedback_case = await find_latest_case_for_feedback(feedback_state)
        if matched_feedback_case is not None:
            await increment_case_success(
                matched_feedback_case.get("id"),
                source_table=str(matched_feedback_case.get("source_table") or "knowledge_cases"),
            )

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
            force_new_conversation=bool(mentioned_car),
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
            localized_answer, = await _localize_text_blocks([matched_case_answer], state.language)
            localized_links = await _localize_links(matched_case_links, state.language)
            answer_text = format_from_kb(
                language=state.language,
                answer=localized_answer,
                links=localized_links,
            )
            await update_user_after_response(
                user,
                normalized,
                answer_text,
                should_decrease_limit=False,
                active_car=state.active_car,
                symptom=state.current_symptom,
                message_type="kb_match",
                links=localized_links,
                vehicle_id=vehicle_id,
                force_new_conversation=bool(mentioned_car),
            )
            return ChatResponse(answer=answer_text, links=localized_links, quota=_quota_payload(user))

    if state.should_search:
        can_run, subscription = can_run_parser(user_id=user.id)
        if not can_run:
            answer_text = (
                "Лимит запросов PULS закончился. Нужен платный тариф, чтобы запустить Parser или Deep Search."
                if state.language == "ru"
                else "Your PULS request limit is exhausted. A paid plan is required to run Parser or Deep Search."
            )
            await update_user_after_response(
                user,
                normalized,
                answer_text,
                should_decrease_limit=False,
                active_car=state.active_car,
                symptom=state.current_symptom,
                message_type="limit",
                vehicle_id=vehicle_id,
                force_new_conversation=bool(mentioned_car),
            )
            return ChatResponse(answer=answer_text, links=[], quota=quota_payload(subscription))

        is_service_detail_turn = bool(
            service_seed_query
            and _looks_like_service_detail_prompt(latest_assistant_text)
            and not _looks_like_service_advice_query(normalized.text)
        )
        if service_flow_active and service_seed_query and _looks_like_service_followup_reply(normalized.text):
            is_service_detail_turn = True
        effective_symptom = state.previous_symptom if state.should_deep_search and state.previous_symptom else state.current_symptom
        if is_service_detail_turn:
            effective_symptom = service_seed_query

        parser_query = effective_symptom
        if is_service_detail_turn and str(normalized.text or "").strip():
            parser_query = _build_service_parser_query(
                language=state.language,
                seed_query=effective_symptom,
                assistant_prompt=latest_assistant_text,
                user_reply=normalized.text,
                service_target=service_target,
            )

        parser_input = normalized.model_copy(update={"text": parser_query})
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
                    "query": parser_query,
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
                service_target=service_target,
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
                should_decrease_limit=False,
                active_car=state.active_car,
                symptom=effective_symptom,
                message_type="parser_fallback",
                links=[],
                parser_used=True,
                deep_search_used=bool(state.should_deep_search),
                vehicle_id=vehicle_id,
                force_new_conversation=bool(mentioned_car),
            )
            return ChatResponse(answer=answer_text, links=[], quota=_quota_payload(user))

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

        has_structured_parser_answer = bool(
            diagnosis_text or probable_causes or first_checks or response_links
        )

        if has_structured_parser_answer and not parser_placeholder:
            localized_blocks = await _localize_text_blocks(
                [diagnosis_text, *probable_causes, *first_checks, *less_likely],
                state.language,
            )
            localized_diagnosis = localized_blocks[0] if localized_blocks else diagnosis_text
            probable_start = 1
            probable_end = probable_start + len(probable_causes)
            checks_end = probable_end + len(first_checks)
            less_end = checks_end + len(less_likely)
            localized_probable_causes = localized_blocks[probable_start:probable_end]
            localized_first_checks = localized_blocks[probable_end:checks_end]
            localized_less_likely = localized_blocks[checks_end:less_end]
            localized_links = await _localize_links(response_links, state.language)
            answer_text = format_technical_answer(
                language=state.language,
                diagnosis=(
                    localized_diagnosis
                    or (localized_probable_causes[0] if localized_probable_causes else "")
                    or (localized_first_checks[0] if localized_first_checks else "")
                ),
                probable_causes=localized_probable_causes,
                first_checks=localized_first_checks[:3],
                less_likely=localized_less_likely,
                links=localized_links,
                question_tail=(
                    "Это помогло решить проблему? Если нет - напишите 'не помогло', и я запущу более глубокий поиск."
                    if state.language == "ru"
                    else "Did this solve the problem? If not, write 'not helped' and I will run a deeper search."
                ),
            )
            response_links = localized_links
        else:
            answer_text = _generic_diagnostic_fallback(
                language=state.language,
                active_car=state.active_car,
                symptom=effective_symptom,
                service_target=service_target,
            )
            answer_text += (
                "\n\nЭто помогло решить проблему? Если нет - напишите 'не помогло', и я запущу более глубокий поиск."
                if state.language == "ru"
                else "\n\nDid this solve the problem? If not, write 'not helped' and I will run a deeper search."
            )

        if _looks_like_service_advice_query(effective_symptom):
            answer_text = _prepend_service_brief(
                answer_text=answer_text,
                language=state.language,
                active_car=state.active_car,
                symptom=effective_symptom,
                service_target=service_target,
            )

        await update_user_after_response(
            user,
            normalized,
            answer_text,
            should_decrease_limit=True,
            active_car=state.active_car,
            symptom=parser_query if is_service_detail_turn else effective_symptom,
            message_type="parser",
            links=response_links,
            parser_used=True,
            deep_search_used=bool(state.should_deep_search),
            vehicle_id=vehicle_id,
            parsed_case=parsed_case,
            force_new_conversation=bool(mentioned_car),
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
        force_new_conversation=bool(mentioned_car),
    )
    return ChatResponse(answer=answer_text, links=[], quota=_quota_payload(user))
