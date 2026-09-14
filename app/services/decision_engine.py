from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schemas.chat import ChatResponse
from app.schemas.router import RouterDecision
from app.services.conversation_service import get_latest_conversation_context
from app.services.diagnostic_context_service import build_diagnostic_context
from app.services.diagnostic_provider import run_diagnostic_provider
from app.services.formatter_service import format_from_kb, format_technical_answer
from app.services.kb_service import (
    _clean_case_answer,
    find_latest_case_for_feedback,
    find_matching_case,
    find_matching_history_case,
    increment_case_success,
)
from app.services.normalize_service import normalize_chat_input
from app.services.openai_service import OpenAIRouterUnavailableError, generate_natural_chat_reply, translate_segments
from app.services.parser_service import ParserUnavailableError, parse_diagnostic
from app.services.puls_data_service import find_reusable_media, resolve_user_vehicle, upsert_reference_media
from app.services.reference_search_service import ReferenceSearchUnavailableError, search_reference
from app.services.response_source_service import filter_response_sources
from app.services.router_service import route_message
from app.services.subscription_service import can_run_parser, ensure_user_subscription, quota_payload
from app.services.user_service import get_or_create_user, update_user_after_response


@dataclass
class FastChatContext:
    mode: str
    language: str
    active_car: str = ""
    vehicle_id: int | None = None
    current_symptom: str = ""
    previous_symptom: str = ""
    problem_class: str = "OTHER"
    search_intent: str = ""
    current_subject: str = ""
    reference_target: str = ""
    case_seed: str = ""
    user_facts: list[str] = field(default_factory=list)
    evidence_links: list[dict] = field(default_factory=list)
    should_search: bool = False
    should_deep_search: bool = False
    needs_clarification: bool = False


_BRAND_PATTERN = re.compile(
    r"\b(toyota|lexus|nissan|infiniti|honda|acura|mazda|subaru|mitsubishi|suzuki|"
    r"bmw|mercedes(?:-benz)?|audi|volkswagen|vw|porsche|opel|skoda|renault|peugeot|"
    r"citroen|fiat|volvo|ford|chevrolet|cadillac|dodge|jeep|chrysler|ram|hyundai|kia|"
    r"genesis|lada)\b(?:\s+[A-Za-z0-9.-]+){0,7}",
    re.IGNORECASE,
)
_ENGINE_PATTERN = re.compile(
    r"\b(?:[1-9][.,]\d\s?(?:l|liter)|v[68]|i[46]|sr20vet|sr20|qr20|qr25|vq35|"
    r"1zz|2zz|2gr|1gr|1g[- ]?gze|1ggze|ej20|ej25|fa20|fb25|k20|k24|m54|m57|n52|n54|n55|b58)\b",
    re.IGNORECASE,
)
_DTC_PATTERN = re.compile(r"\b[pucb]\d{4}\b", re.IGNORECASE)


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


def _normalize_phrase(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _word_count(text: str) -> int:
    return len([part for part in re.split(r"\s+", str(text or "").strip()) if part])


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = _normalize_phrase(text)
    return any(term in lowered for term in terms)


def _plain_text_response(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", cleaned)
    cleaned = cleaned.replace("**", "").replace("__", "")
    cleaned = re.sub(r"(?m)^\s*[-*]\s+", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_active_car_from_text(text: str) -> str:
    raw = " ".join(str(text or "").replace(",", " ").split())
    match = _BRAND_PATTERN.search(raw)
    if not match:
        return ""
    label = match.group(0).strip(" .,:;!?")
    year = re.search(r"\b(19[8-9]\d|20[0-3]\d)\b", raw)
    engine = _ENGINE_PATTERN.search(raw)
    if year and year.group(0) not in label:
        label = f"{label} {year.group(0)}"
    if engine and engine.group(0).lower() not in label.lower():
        label = f"{label} {engine.group(0)}"
    return label


def _vehicle_label(vehicle: dict | None) -> str:
    vehicle = vehicle or {}
    parts = [vehicle.get("brand"), vehicle.get("model"), vehicle.get("year"), vehicle.get("engine")]
    return " ".join(str(part).strip() for part in parts if str(part or "").strip()).strip()


def _resolve_vehicle(*, user_id: int | None, car_text: str) -> tuple[int | None, str, dict | None]:
    if user_id is None or not str(car_text or "").strip():
        return None, str(car_text or "").strip(), None
    vehicle = resolve_user_vehicle(user_id=user_id, car_text=car_text)
    label = _vehicle_label(vehicle)
    if vehicle and label:
        return vehicle.get("id"), label, vehicle
    return None, str(car_text or "").strip(), vehicle


def _is_social_general_text(text: str) -> bool:
    lowered = _normalize_phrase(text).strip(" .,:;!?")
    if not lowered:
        return False
    if _contains_any(lowered, _AUTOMOTIVE_TERMS) or _extract_active_car_from_text(lowered):
        return False
    social_terms = (
        "hi",
        "hello",
        "hey",
        "how are you",
        "how's it going",
        "thanks",
        "thank you",
        "ok",
        "okay",
        "\u043f\u0440\u0438\u0432\u0435\u0442",
        "\u043a\u0430\u043a \u0434\u0435\u043b\u0430",
        "\u043a\u0430\u043a \u0442\u044b",
        "\u043a\u0430\u043a \u0436\u0438\u0437\u043d\u044c",
        "\u0441\u043f\u0430\u0441\u0438\u0431\u043e",
        "\u043e\u043a",
        "\u043e\u043a\u0435\u0439",
    )
    return _word_count(lowered) <= 6 and any(term in lowered for term in social_terms)


_AUTOMOTIVE_TERMS = (
    "engine",
    "motor",
    "idle",
    "rpm",
    "dtc",
    "obd",
    "check engine",
    "vibration",
    "vibrates",
    "stall",
    "stalls",
    "noise",
    "misfire",
    "acceleration",
    "under load",
    "cold",
    "hot",
    "warm",
    "after replacement",
    "replaced",
    "repair",
    "oil",
    "fluid",
    "\u043c\u0430\u0448\u0438\u043d",
    "\u0434\u0432\u0438\u0433\u0430\u0442",
    "\u043c\u043e\u0442\u043e\u0440",
    "\u0445\u043e\u043b\u043e\u0441\u0442",
    "\u043e\u0431\u043e\u0440\u043e\u0442",
    "\u0432\u0438\u0431\u0440\u0430\u0446",
    "\u0442\u0440\u043e\u0438\u0442",
    "\u043d\u0435 \u0442\u044f\u043d\u0435\u0442",
    "\u0440\u0430\u0437\u0433\u043e\u043d",
    "\u043d\u0430\u0433\u0440\u0443\u0437",
    "\u0445\u043e\u043b\u043e\u0434",
    "\u0433\u043e\u0440\u044f\u0447",
    "\u043f\u0440\u043e\u0433\u0440\u0435\u0432",
    "\u043f\u043e\u0441\u043b\u0435",
    "\u0437\u0430\u043c\u0435\u043d",
    "\u043e\u0448\u0438\u0431",
    "\u0447\u0435\u043a",
    "\u0441\u0442\u0443\u043a",
    "\u0448\u0443\u043c",
    "\u043c\u0430\u0441\u043b\u043e",
    "\u0436\u0438\u0434\u043a",
)


def _has_automotive_content(text: str) -> bool:
    return bool(_extract_active_car_from_text(text) or _DTC_PATTERN.search(str(text or "")) or _contains_any(text, _AUTOMOTIVE_TERMS))


def _looks_like_source_question(text: str) -> bool:
    return _contains_any(
        text,
        (
            "source",
            "sources",
            "where did",
            "evidence",
            "why do you think",
            "\u043e\u0442\u043a\u0443\u0434\u0430",
            "\u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a",
            "\u043f\u043e\u0447\u0435\u043c\u0443 \u0442\u044b \u0442\u0430\u043a",
        ),
    )


def _looks_like_detail_request(text: str) -> bool:
    return _contains_any(
        text,
        (
            "details",
            "more information",
            "tell me more",
            "other variants",
            "\u043f\u043e\u0434\u0440\u043e\u0431\u043d",
            "\u0435\u0449\u0435 \u0432\u0430\u0440\u0438\u0430\u043d",
            "\u0435\u0449\u0451 \u0432\u0430\u0440\u0438\u0430\u043d",
        ),
    )


def _looks_like_visual_request(text: str) -> bool:
    return _contains_any(
        text,
        (
            "what does it look like",
            "show me",
            "photo",
            "picture",
            "image",
            "where exactly",
            "how it looks",
            "\u043a\u0430\u043a \u0432\u044b\u0433\u043b\u044f\u0434",
            "\u043f\u043e\u043a\u0430\u0436",
            "\u0444\u043e\u0442\u043e",
            "\u043a\u0430\u0440\u0442\u0438\u043d",
            "\u0433\u0434\u0435 \u0438\u043c\u0435\u043d\u043d\u043e",
        ),
    )


def _looks_like_video_request(text: str) -> bool:
    return _contains_any(text, ("video", "youtube", "clip", "\u0432\u0438\u0434\u0435\u043e", "\u044e\u0442\u0443\u0431"))


def _looks_like_link_request(text: str) -> bool:
    return _contains_any(
        text,
        (
            "link",
            "url",
            "source",
            "manual",
            "reference",
            "\u0441\u0441\u044b\u043b",
            "\u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a",
            "\u043c\u0430\u043d\u0443\u0430\u043b",
        ),
    )


def _looks_like_reference_request(text: str) -> bool:
    return _contains_any(
        text,
        (
            "where is",
            "where located",
            "where can i find",
            "identification number",
            "engine number",
            "part number",
            "how to find",
            "\u0433\u0434\u0435 \u043d\u0430\u0445\u043e\u0434",
            "\u0433\u0434\u0435 \u0441\u0442\u043e\u0438\u0442",
            "\u043d\u043e\u043c\u0435\u0440 \u0434\u0432\u0438\u0433",
            "\u043d\u043e\u043c\u0435\u0440 \u043c\u043e\u0442\u043e\u0440",
            "\u043a\u0430\u043a \u043d\u0430\u0439\u0442\u0438",
            "\u043a\u0430\u0442\u0430\u043b\u043e\u0436\u043d",
        ),
    ) or _looks_like_visual_request(text) or _looks_like_video_request(text) or _looks_like_link_request(text)


def _classify_problem(text: str) -> str:
    lowered = _normalize_phrase(text)
    classes = (
        ("NO_START", ("no start", "won't start", "does not start", "cranks", "no crank", "\u043d\u0435 \u0437\u0430\u0432\u043e\u0434", "\u043a\u0440\u0443\u0442\u0438\u0442", "\u0441\u0442\u0430\u0440\u0442\u0435\u0440")),
        ("HARD_START", ("hard start", "starts badly", "\u043f\u043b\u043e\u0445\u043e \u0437\u0430\u0432\u043e\u0434", "\u0434\u043e\u043b\u0433\u043e \u0437\u0430\u0432\u043e\u0434")),
        ("STALL", ("stall", "stalls", "\u0433\u043b\u043e\u0445", "\u0437\u0430\u0433\u043b\u043e\u0445")),
        ("MISFIRE", ("misfire", "troits", "\u0442\u0440\u043e\u0438\u0442", "\u043f\u0440\u043e\u043f\u0443\u0441\u043a")),
        ("VIBRATION", ("vibration", "vibrates", "\u0432\u0438\u0431\u0440\u0430\u0446")),
        ("NOISE", ("noise", "knock", "rattle", "hum", "\u0448\u0443\u043c", "\u0441\u0442\u0443\u043a", "\u0433\u0443\u043b")),
        ("POWER_LOSS", ("power loss", "no power", "loss of power", "doesn't pull", "under load", "\u043d\u0435 \u0442\u044f\u043d\u0435\u0442", "\u043f\u043e\u0442\u0435\u0440\u044f \u0442\u044f\u0433", "\u043d\u0430\u0433\u0440\u0443\u0437")),
        ("OVERHEATING", ("overheat", "temperature", "\u043f\u0435\u0440\u0435\u0433\u0440\u0435", "\u0442\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440")),
        ("FLUID_CONSUMPTION", ("oil consumption", "burns oil", "uses oil", "\u0436\u0440\u0435\u0442 \u043c\u0430\u0441\u043b", "\u0440\u0430\u0441\u0445\u043e\u0434 \u043c\u0430\u0441\u043b")),
        ("WARNING_DTC", ("dtc", "obd", "check engine", "\u043e\u0448\u0438\u0431", "\u0447\u0435\u043a")),
        ("TRANSMISSION", ("transmission", "gearbox", "cvt", "atf", "\u043a\u043e\u0440\u043e\u0431\u043a", "\u0430\u043a\u043f\u043f", "\u0432\u0430\u0440\u0438\u0430\u0442\u043e\u0440")),
        ("BRAKING", ("brake", "\u0442\u043e\u0440\u043c\u043e\u0437")),
        ("ELECTRICAL", ("electrical", "battery", "alternator", "fuse", "\u044d\u043b\u0435\u043a\u0442\u0440", "\u0430\u043a\u043a\u0443\u043c", "\u0433\u0435\u043d\u0435\u0440\u0430\u0442\u043e\u0440", "\u043f\u0440\u0435\u0434\u043e\u0445\u0440")),
        ("SERVICE_REFERENCE", ("oil", "fluid", "coolant", "service", "\u043c\u0430\u0441\u043b\u043e", "\u0436\u0438\u0434\u043a", "\u0430\u043d\u0442\u0438\u0444\u0440\u0438\u0437", "\u0441\u0435\u0440\u0432\u0438\u0441")),
        ("ENGINE_IDENTIFICATION", ("engine number", "identification number", "\u043d\u043e\u043c\u0435\u0440 \u0434\u0432\u0438\u0433", "\u043d\u043e\u043c\u0435\u0440 \u043c\u043e\u0442\u043e\u0440")),
        ("PART_IDENTIFICATION", ("part number", "which part", "\u043a\u0430\u0442\u0430\u043b\u043e\u0436\u043d", "\u043a\u0430\u043a\u0430\u044f \u0434\u0435\u0442\u0430\u043b")),
        ("HOW_TO_REFERENCE", ("how to", "manual", "\u043a\u0430\u043a ", "\u043c\u0430\u043d\u0443\u0430\u043b")),
    )
    for label, terms in classes:
        if any(term in lowered for term in terms):
            return label
    return "OTHER"


def _classify_search_intent(text: str, problem_class: str, previous_subject: str = "") -> str:
    if _DTC_PATTERN.search(str(text or "")):
        return "DIAGNOSTIC_SEARCH"
    if _looks_like_video_request(text):
        return "VIDEO_REFERENCE"
    if _looks_like_visual_request(text):
        return "IMAGE_REFERENCE"
    if _looks_like_link_request(text) or _looks_like_reference_request(text):
        if "manual" in _normalize_phrase(text) or "\u043c\u0430\u043d\u0443\u0430\u043b" in _normalize_phrase(text):
            return "MANUAL_SEARCH"
        return "REFERENCE_SEARCH"
    if problem_class in {"ENGINE_IDENTIFICATION", "PART_IDENTIFICATION", "HOW_TO_REFERENCE", "SERVICE_REFERENCE"}:
        return "REFERENCE_SEARCH"
    if previous_subject and _word_count(text) <= 5 and _looks_like_reference_request(text):
        return "REFERENCE_SEARCH"
    return "DIAGNOSTIC_SEARCH"


def _infer_reference_target(text: str, previous_target: str = "") -> str:
    lowered = _normalize_phrase(text)
    if any(term in lowered for term in ("engine number", "identification number", "\u043d\u043e\u043c\u0435\u0440 \u0434\u0432\u0438\u0433", "\u043d\u043e\u043c\u0435\u0440 \u043c\u043e\u0442\u043e\u0440")):
        return "ENGINE_NUMBER_LOCATION"
    if any(term in lowered for term in ("part number", "\u043a\u0430\u0442\u0430\u043b\u043e\u0436\u043d")):
        return "PART_REFERENCE"
    if _looks_like_visual_request(text) or _looks_like_video_request(text) or _looks_like_link_request(text):
        return previous_target
    return previous_target


def _latest_reference_target(latest_context: dict | None) -> str:
    for item in reversed((latest_context or {}).get("recent_messages") or []):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "")
        target = _infer_reference_target(text, "")
        if target:
            return target
    return ""


def _looks_like_meta_followup(text: str, previous_assistant: str) -> bool:
    lowered = _normalize_phrase(text)
    previous = _normalize_phrase(previous_assistant)
    if not lowered:
        return False
    if _is_social_general_text(text):
        return False
    if _has_automotive_content(lowered) or _extract_active_car_from_text(lowered):
        return False

    memory_or_context_reference = _contains_any(
        lowered,
        (
            "remember",
            "memory",
            "context",
            "previous chat",
            "conversation",
            "what you said",
            "what you meant",
            "\u043f\u043e\u043c\u043d",
            "\u0437\u0430\u043f\u043e\u043c\u043d",
            "\u043f\u0435\u0440\u0435\u043f\u0438\u0441",
            "\u0438\u0441\u0442\u043e\u0440\u0438",
            "\u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442",
            "\u0447\u0442\u043e \u0442\u044b \u0441\u043a\u0430\u0437\u0430\u043b",
            "\u0447\u0442\u043e \u0442\u044b \u0438\u043c\u0435\u043b",
        ),
    )
    if memory_or_context_reference and previous:
        return True

    if not previous:
        return False

    asks_about_statement = lowered.endswith("?") or _contains_any(
        lowered,
        (
            "what",
            "why",
            "mean",
            "meaning",
            "context",
            "\u0447\u0442\u043e",
            "\u043f\u043e\u0447\u0435\u043c\u0443",
            "\u043a\u0430\u043a\u043e\u0439",
            "\u043a\u0430\u043a\u043e\u0433\u043e",
            "\u043f\u0440\u043e",
            "\u0437\u043d\u0430\u0447\u0438\u0442",
            "\u0441\u043c\u044b\u0441\u043b",
        ),
    )
    refers_to_assistant = _contains_any(
        lowered,
        (
            "you",
            "your",
            "that",
            "this",
            "said",
            "meant",
            "\u0442\u044b",
            "\u044d\u0442\u043e",
            "\u044d\u0442\u043e\u0442",
            "\u044d\u0442\u0438\u043c",
            "\u0441\u043a\u0430\u0437\u0430\u043b",
            "\u0438\u043c\u0435\u0435\u0448\u044c",
            "\u0438\u043c\u0435\u043b",
            "\u0432\u0432\u0438\u0434\u0443",
        ),
    )
    overlaps_previous_wording = any(
        token in previous
        for token in lowered.split()
        if len(token) >= 5 and token not in {"\u043a\u0430\u043a\u043e\u0439", "\u043a\u0430\u043a\u043e\u0433\u043e", "which", "what"}
    )
    return asks_about_statement and (refers_to_assistant or overlaps_previous_wording)


def _looks_like_context_capability_question(text: str) -> bool:
    lowered = _normalize_phrase(text)
    if not lowered:
        return False
    asks_about_assistant = _contains_any(
        lowered,
        (
            "will you",
            "can you",
            "do you",
            "you remember",
            "puls remember",
            "\u0442\u044b",
            "\u0431\u0443\u0434\u0435\u0448\u044c",
            "\u0441\u043c\u043e\u0436\u0435\u0448\u044c",
            "puls",
        ),
    )
    asks_about_persistence = _contains_any(
        lowered,
        (
            "remember",
            "saved",
            "profile",
            "my car",
            "next conversation",
            "next chat",
            "\u043f\u043e\u043c\u043d",
            "\u0441\u043e\u0445\u0440\u0430\u043d",
            "\u0440\u0430\u0437\u0434\u0435\u043b",
            "\u043c\u043e\u0439 \u0430\u0432\u0442\u043e\u043c\u043e\u0431\u0438\u043b",
            "\u043c\u043e\u044f \u043c\u0430\u0448\u0438\u043d",
            "\u0441\u043b\u0435\u0434\u0443\u044e\u0449",
        ),
    )
    return asks_about_assistant and asks_about_persistence


def _looks_like_vehicle_profile_question(text: str) -> bool:
    lowered = _normalize_phrase(text)
    if not lowered:
        return False
    asks_about_owned_vehicle = _contains_any(
        lowered,
        (
            "what car",
            "which car",
            "my car",
            "saved car",
            "vehicle profile",
            "\u043a\u0430\u043a\u0430\u044f \u0443 \u043c\u0435\u043d\u044f",
            "\u043a\u0430\u043a\u043e\u0439 \u0443 \u043c\u0435\u043d\u044f",
            "\u043c\u043e\u044f \u043c\u0430\u0448\u0438\u043d",
            "\u043c\u043e\u0439 \u0430\u0432\u0442\u043e\u043c\u043e\u0431\u0438\u043b",
            "\u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u043d\u0430\u044f \u043c\u0430\u0448\u0438\u043d",
        ),
    )
    asks_for_fault_or_service = _contains_any(
        lowered,
        (
            "problem",
            "fault",
            "diagnos",
            "oil",
            "fluid",
            "repair",
            "\u043f\u0440\u043e\u0431\u043b\u0435\u043c",
            "\u043d\u0435\u0438\u0441\u043f\u0440\u0430\u0432",
            "\u0434\u0438\u0430\u0433\u043d",
            "\u043c\u0430\u0441\u043b",
            "\u0436\u0438\u0434\u043a",
            "\u0440\u0435\u043c\u043e\u043d\u0442",
        ),
    )
    return asks_about_owned_vehicle and not asks_for_fault_or_service


def _looks_like_feedback_not_helped(text: str, decision: RouterDecision) -> bool:
    return bool(
        decision.user_says_not_helped
        or decision.message_type == "followup_deep"
        or _contains_any(text, ("not helped", "did not help", "\u043d\u0435 \u043f\u043e\u043c\u043e\u0433\u043b\u043e", "\u0438\u0449\u0438 \u0433\u043b\u0443\u0431\u0436\u0435"))
    )


def _looks_like_feedback_helped(text: str, decision: RouterDecision) -> bool:
    return bool(
        decision.user_says_helped
        or decision.message_type == "helped_feedback"
        or _normalize_phrase(text) in {"helped", "fixed", "solved", "\u043f\u043e\u043c\u043e\u0433\u043b\u043e", "\u0440\u0435\u0448\u0435\u043d\u043e"}
    )


def _assistant_asked_clarification(text: str) -> bool:
    return _contains_any(
        text,
        (
            "single most useful condition",
            "are there any dtc",
            "did anything get repaired",
            "when does",
            "\u0443\u0442\u043e\u0447\u043d",
            "\u043a\u043e\u0433\u0434\u0430",
            "\u0435\u0441\u0442\u044c \u043b\u0438",
            "\u0447\u0442\u043e-\u0442\u043e \u043c\u0435\u043d\u044f\u043b\u0438",
        ),
    )


def _pending_question(latest_context: dict | None) -> str:
    last_assistant = str((latest_context or {}).get("last_assistant_text") or "").strip()
    if last_assistant and ("?" in last_assistant or _assistant_asked_clarification(last_assistant)):
        return last_assistant
    for item in reversed((latest_context or {}).get("recent_messages") or []):
        if not isinstance(item, dict) or str(item.get("role") or "").lower() != "assistant":
            continue
        text = str(item.get("text") or "").strip()
        if text and ("?" in text or _assistant_asked_clarification(text)):
            return text
    return ""


def _looks_like_case_related_reply(*, text: str, latest_context: dict | None, active_car: str, case_seed: str) -> bool:
    if not active_car and not case_seed:
        return False
    if _is_social_general_text(text) or _looks_like_context_capability_question(text) or _looks_like_vehicle_profile_question(text):
        return False
    if _looks_like_feedback_helped(text, RouterDecision()) or _looks_like_feedback_not_helped(text, RouterDecision()):
        return True
    if _looks_like_reference_request(text):
        return True

    question = _pending_question(latest_context)
    if not question:
        return False

    current = _normalize_phrase(text)
    if not current:
        return False

    has_case_detail = _contains_case_detail(current) or _DTC_PATTERN.search(current)
    relation_markers = (
        "yes",
        "no",
        "not",
        "cannot",
        "can't",
        "doesn't",
        "still",
        "normal",
        "normally",
        "same",
        "sometimes",
        "always",
        "only",
        "after",
        "before",
        "cold",
        "hot",
        "idle",
        "unknown",
        "don't know",
        "not sure",
        "\u0434\u0430",
        "\u043d\u0435\u0442",
        "\u043d\u043e\u0440\u043c",
        "\u0438\u043d\u043e\u0433\u0434\u0430",
        "\u0432\u0441\u0435\u0433\u0434\u0430",
        "\u0442\u043e\u043b\u044c\u043a\u043e",
        "\u043f\u043e\u0441\u043b\u0435",
        "\u0434\u043e",
        "\u0445\u043e\u043b\u043e\u0434",
        "\u0433\u043e\u0440\u044f\u0447",
        "\u0445\u043e\u043b\u043e\u0441\u0442",
        "\u043d\u0435 \u0437\u043d\u0430\u044e",
    )
    has_relation_language = any(marker in current for marker in relation_markers)
    concise_answer = _word_count(current) <= 14 and not current.endswith("?")
    return bool(has_case_detail or (concise_answer and has_relation_language))


def _contains_case_detail(text: str) -> bool:
    return bool(
        _DTC_PATTERN.search(str(text or ""))
        or _contains_any(
            text,
            (
                "cold",
                "hot",
                "warm",
                "idle",
                "under load",
                "acceleration",
                "after",
                "replaced",
                "replacement",
                "dtc",
                "\u0445\u043e\u043b\u043e\u0434",
                "\u0433\u043e\u0440\u044f\u0447",
                "\u043f\u0440\u043e\u0433\u0440\u0435\u0432",
                "\u0445\u043e\u043b\u043e\u0441\u0442",
                "\u0440\u0430\u0437\u0433\u043e\u043d",
                "\u043d\u0430\u0433\u0440\u0443\u0437",
                "\u043f\u043e\u0441\u043b\u0435",
                "\u0437\u0430\u043c\u0435\u043d",
                "\u043e\u0448\u0438\u0431",
            ),
        )
    )


def _enough_context_for_knowledge(text: str, case_seed: str) -> bool:
    combined = " ".join(part for part in (case_seed, text) if part).strip()
    lowered = _normalize_phrase(combined)
    has_repair_or_code = bool(
        _DTC_PATTERN.search(combined)
        or any(marker in lowered for marker in ("replaced", "replacement", "repair", "after right axle", "\u0437\u0430\u043c\u0435\u043d", "\u0440\u0435\u043c\u043e\u043d\u0442"))
    )
    detail_score = sum(
        1
        for marker in (
            "cold",
            "hot",
            "warm",
            "acceleration",
            "under load",
            "after",
            "replacement",
            "dtc",
            "\u0445\u043e\u043b\u043e\u0434",
            "\u0433\u043e\u0440\u044f\u0447",
            "\u043f\u0440\u043e\u0433\u0440\u0435\u0432",
            "\u0440\u0430\u0437\u0433\u043e\u043d",
            "\u043f\u043e\u0441\u043b\u0435",
            "\u0437\u0430\u043c\u0435\u043d",
            "\u043e\u0448\u0438\u0431",
        )
        if marker in lowered
    )
    return has_repair_or_code and (_DTC_PATTERN.search(combined) is not None or (_word_count(combined) >= 8 and detail_score >= 3))


def _latest_non_social_user_text(latest_context: dict | None, history: str = "") -> str:
    messages = (latest_context or {}).get("recent_messages") or []
    if isinstance(messages, list):
        for item in reversed(messages):
            if not isinstance(item, dict):
                continue
            if str(item.get("role") or "").lower() != "user":
                continue
            text = str(item.get("text") or "").strip()
            if text and not _is_social_general_text(text) and (_has_automotive_content(text) or _word_count(text) > 3):
                return text
    return _extract_last_history_value(history, "symptom")


def _build_case_seed(latest_context: dict | None, history: str, current_text: str) -> str:
    seed = _latest_non_social_user_text(latest_context, history)
    if not seed:
        return current_text.strip()
    if current_text.strip() and current_text.strip() != seed and not _is_social_general_text(current_text):
        return f"{seed}. Additional user information: {current_text.strip()}"
    return seed


def _extract_last_history_value(history: str, key: str) -> str:
    blocks = [block.strip() for block in str(history or "").split("\n---\n") if block.strip()]
    for block in reversed(blocks):
        for line in reversed(block.splitlines()):
            if line.lower().startswith(f"{key.lower()}:"):
                return line.split(":", 1)[1].strip()
    return ""


def _parse_latest_evidence(history: str) -> dict:
    blocks = [block.strip() for block in str(history or "").split("\n---\n") if block.strip()]
    for block in reversed(blocks):
        fields: dict[str, str] = {}
        links: list[dict] = []
        in_links = False
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.lower() == "links:":
                in_links = True
                continue
            if in_links and line.startswith("- "):
                title, _, url = line[2:].partition(": ")
                links.append({"title": title.strip() or url.strip(), "url": url.strip() or title.strip(), "description": "", "type": "link"})
                continue
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key.strip().lower()] = value.strip()
        if fields.get("assistant") or links:
            fields["links"] = links
            return fields
    return {}


def _stored_evidence_answer(*, language: str, history: str) -> tuple[str, list[dict]] | None:
    evidence = _parse_latest_evidence(history)
    if not evidence:
        return None
    links = evidence.get("links") or []
    answer = evidence.get("assistant") or ""
    symptom = evidence.get("symptom") or evidence.get("user") or ""
    if language == "ru":
        text = "\u041e\u043f\u0438\u0440\u0430\u044e\u0441\u044c \u043d\u0430 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u043d\u044b\u0439 \u043a\u0435\u0439\u0441"
        if symptom:
            text += f": {symptom}"
        if answer:
            text += f"\n\n\u041a\u0440\u0430\u0442\u043a\u043e: {answer}"
    else:
        text = "I am using the current stored case"
        if symptom:
            text += f": {symptom}"
        if answer:
            text += f"\n\nIn short: {answer}"
    return text, links


def _general_conversation_text(language: str, assistant_hint: str = "", user_text: str = "") -> str:
    if assistant_hint and assistant_hint.strip():
        return assistant_hint.strip()
    lowered = _normalize_phrase(user_text)
    if language == "ru":
        if "\u0441\u043f\u0430\u0441\u0438\u0431" in lowered:
            return "\u041f\u043e\u0436\u0430\u043b\u0443\u0439\u0441\u0442\u0430. \u042f \u043d\u0430 \u0441\u0432\u044f\u0437\u0438."
        return "\u041d\u043e\u0440\u043c\u0430\u043b\u044c\u043d\u043e, \u044f \u043d\u0430 \u0441\u0432\u044f\u0437\u0438. \u041f\u043e \u043c\u0430\u0448\u0438\u043d\u0435 \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442 \u043d\u0435 \u043f\u043e\u0442\u0435\u0440\u044f\u043b."
    if "thank" in lowered:
        return "You are welcome. I am here."
    return "Doing fine, and I am here when you want to continue."


def _meta_conversation_text(*, language: str, user_text: str, previous_assistant: str, active_car: str) -> str:
    if language == "ru":
        if active_car:
            return (
                f"\u042f \u043f\u0440\u043e \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442 \u043c\u0430\u0448\u0438\u043d\u044b, \u043a\u043e\u0442\u043e\u0440\u0443\u044e \u043c\u044b \u043e\u0431\u0441\u0443\u0436\u0434\u0430\u043b\u0438: {active_car}. "
                "\u0418\u043c\u0435\u043b \u0432 \u0432\u0438\u0434\u0443, \u0447\u0442\u043e \u0438\u0441\u0442\u043e\u0440\u0438\u044f \u044d\u0442\u043e\u0433\u043e \u0440\u0430\u0437\u0433\u043e\u0432\u043e\u0440\u0430 \u043e\u0441\u0442\u0430\u043b\u0430\u0441\u044c \u0443 \u043c\u0435\u043d\u044f \u0432 \u0444\u043e\u043d\u0435."
            )
        return "\u042f \u0438\u043c\u0435\u043b \u0432 \u0432\u0438\u0434\u0443 \u043f\u0440\u0435\u0434\u044b\u0434\u0443\u0449\u0443\u044e \u0440\u0435\u043f\u043b\u0438\u043a\u0443 \u0438 \u0445\u043e\u0434 \u0440\u0430\u0437\u0433\u043e\u0432\u043e\u0440\u0430. \u041d\u0435 \u0437\u0430\u043f\u0443\u0441\u043a\u0430\u044e \u0434\u0438\u0430\u0433\u043d\u043e\u0441\u0442\u0438\u043a\u0443, \u043f\u0440\u043e\u0441\u0442\u043e \u0443\u0442\u043e\u0447\u043d\u044f\u044e, \u0447\u0442\u043e \u043c\u044b \u043f\u043e\u043d\u044f\u043b\u0438 \u0434\u0440\u0443\u0433 \u0434\u0440\u0443\u0433\u0430."
    if active_car:
        return f"I meant the car context we had been discussing: {active_car}. I was saying I still have that conversation context in the background."
    return "I meant my previous reply and the thread of the conversation. I am not starting diagnostics from that question."


def _recent_messages(latest_context: dict | None) -> list[dict]:
    messages = (latest_context or {}).get("recent_messages") or []
    if not isinstance(messages, list):
        return []
    result = []
    for item in messages[-8:]:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "role": str(item.get("role") or "").strip(),
                "text": str(item.get("text") or "").strip(),
            }
        )
    return result


async def _natural_chat_text(
    *,
    mode: str,
    context: FastChatContext,
    normalized,
    latest_context: dict | None,
    assistant_hint: str = "",
    fallback: str = "",
) -> str:
    context_relevant = mode in {"META_CHAT", "CLARIFICATION"} or _looks_like_context_capability_question(
        str(normalized.text or "")
    ) or _looks_like_vehicle_profile_question(str(normalized.text or ""))
    recent_conversation = _recent_messages(latest_context) if context_relevant else []
    active_vehicle = context.active_car if context_relevant else ""
    automotive_context = context.case_seed if context_relevant else ""
    stored_facts = context.user_facts if context_relevant else []
    try:
        reply = await generate_natural_chat_reply(
            mode=mode,
            user_text=str(normalized.text or ""),
            language=context.language,
            recent_conversation=recent_conversation,
            active_vehicle=active_vehicle,
            automotive_context=automotive_context,
            pending_clarification=fallback if mode == "CLARIFICATION" else "",
            stored_facts=stored_facts,
            context_relevant=context_relevant,
        )
    except (OpenAIRouterUnavailableError, Exception):
        reply = assistant_hint or fallback
    return _plain_text_response(reply or fallback)


def _clarification_text(*, language: str, active_car: str, symptom: str, problem_class: str = "OTHER", stage: int = 1) -> str:
    car = f" \u043f\u043e {active_car}" if language == "ru" and active_car else f" on {active_car}" if active_car else ""
    if language == "ru":
        if problem_class == "NO_START":
            return f"\u041f\u043e\u043d\u044f\u043b{car}. \u0421\u0442\u0430\u0440\u0442\u0435\u0440 \u043a\u0440\u0443\u0442\u0438\u0442 \u0434\u0432\u0438\u0433\u0430\u0442\u0435\u043b\u044c, \u0438\u043b\u0438 \u0432\u043e\u043e\u0431\u0449\u0435 \u043d\u0435\u0442 \u043f\u0440\u043e\u043a\u0440\u0443\u0442\u043a\u0438?"
        if problem_class == "VIBRATION":
            return f"\u041f\u043e\u043d\u044f\u043b{car}. \u0413\u0434\u0435 \u0432\u0438\u0431\u0440\u0430\u0446\u0438\u044f \u0441\u0438\u043b\u044c\u043d\u0435\u0435: \u043d\u0430 \u0445\u043e\u043b\u043e\u0441\u0442\u044b\u0445, \u043d\u0430 \u0441\u043a\u043e\u0440\u043e\u0441\u0442\u0438, \u043f\u0440\u0438 \u0440\u0430\u0437\u0433\u043e\u043d\u0435 \u0438\u043b\u0438 \u043f\u043e\u0434 \u043d\u0430\u0433\u0440\u0443\u0437\u043a\u043e\u0439?"
        if problem_class == "NOISE":
            return f"\u041f\u043e\u043d\u044f\u043b{car}. \u0428\u0443\u043c \u0437\u0430\u0432\u0438\u0441\u0438\u0442 \u0431\u043e\u043b\u044c\u0448\u0435 \u043e\u0442 \u043e\u0431\u043e\u0440\u043e\u0442\u043e\u0432 \u0434\u0432\u0438\u0433\u0430\u0442\u0435\u043b\u044f \u0438\u043b\u0438 \u043e\u0442 \u0441\u043a\u043e\u0440\u043e\u0441\u0442\u0438 \u043c\u0430\u0448\u0438\u043d\u044b?"
        if problem_class == "POWER_LOSS":
            return f"\u041f\u043e\u043d\u044f\u043b{car}. \u0422\u044f\u0433\u0430 \u043f\u0440\u043e\u043f\u0430\u0434\u0430\u0435\u0442 \u043d\u0430 \u0445\u043e\u043b\u043e\u0434\u043d\u0443\u044e, \u043d\u0430 \u0433\u043e\u0440\u044f\u0447\u0443\u044e, \u043f\u043e\u0434 \u043d\u0430\u0433\u0440\u0443\u0437\u043a\u043e\u0439 \u0438\u043b\u0438 \u0432\u0441\u0435\u0433\u0434\u0430?"
        if stage >= 2 or _contains_case_detail(symptom):
            return f"\u041f\u0440\u0438\u043d\u044f\u043b{car}. \u0415\u0441\u0442\u044c \u043b\u0438 \u043e\u0448\u0438\u0431\u043a\u0438/DTC \u0438\u043b\u0438 \u0447\u0442\u043e-\u0442\u043e \u043c\u0435\u043d\u044f\u043b\u0438 \u043f\u0435\u0440\u0435\u0434 \u0442\u0435\u043c, \u043a\u0430\u043a \u044d\u0442\u043e \u043d\u0430\u0447\u0430\u043b\u043e\u0441\u044c?"
        return f"\u041f\u043e\u043d\u044f\u043b \u043a\u0435\u0439\u0441{car}. \u0423\u0442\u043e\u0447\u043d\u0438 \u043e\u0434\u0438\u043d \u043c\u043e\u043c\u0435\u043d\u0442: \u043a\u043e\u0433\u0434\u0430 \u043f\u0440\u043e\u044f\u0432\u043b\u044f\u0435\u0442\u0441\u044f - \u043d\u0430 \u0445\u043e\u043b\u043e\u0434\u043d\u0443\u044e, \u043d\u0430 \u0433\u043e\u0440\u044f\u0447\u0443\u044e, \u043d\u0430 \u0445\u043e\u043b\u043e\u0441\u0442\u044b\u0445, \u043f\u043e\u0434 \u043d\u0430\u0433\u0440\u0443\u0437\u043a\u043e\u0439 \u0438\u043b\u0438 \u043f\u043e\u0441\u043b\u0435 \u0437\u0430\u043c\u0435\u043d\u044b?"
    if problem_class == "NO_START":
        return f"Understood{car}. Does the starter crank the engine, or is there no crank at all?"
    if problem_class == "VIBRATION":
        return f"Got it{car}. Is the vibration strongest at idle, at road speed, during acceleration, or under load?"
    if problem_class == "NOISE":
        return f"Got it{car}. Does the noise follow engine RPM or vehicle speed?"
    if problem_class == "POWER_LOSS":
        return f"Got it{car}. Is the power loss cold, hot, under load, or present all the time?"
    if stage >= 2 or _contains_case_detail(symptom):
        return f"Understood{car}. Are there any DTCs or recent repairs/replacements before it started?"
    return f"Got the case{car}. What is the single most useful condition: cold, hot, idle, under load, or after a recent repair?"


def _fallback_diagnostic_text(*, language: str, active_car: str, symptom: str) -> str:
    if language == "ru":
        car = f" \u043f\u043e {active_car}" if active_car else ""
        return f"\u041f\u043e\u043a\u0430 \u0434\u0430\u043c \u0431\u0430\u0437\u043e\u0432\u044b\u0439 \u043e\u0440\u0438\u0435\u043d\u0442\u0438\u0440{car}: \u043f\u0440\u043e\u0432\u0435\u0440\u044c \u043e\u0448\u0438\u0431\u043a\u0438, \u0440\u0430\u0437\u044a\u0435\u043c\u044b, \u0436\u0438\u0434\u043a\u043e\u0441\u0442\u0438 \u0438 \u0443\u0441\u043b\u043e\u0432\u0438\u044f, \u043a\u043e\u0433\u0434\u0430 \u043f\u0440\u043e\u044f\u0432\u043b\u044f\u0435\u0442\u0441\u044f \u0441\u0438\u043c\u043f\u0442\u043e\u043c: {symptom}."
    car = f" on {active_car}" if active_car else ""
    return f"Initial direction{car}: check DTCs, connectors, fluids, and the exact conditions when this happens: {symptom}."


def _reference_answer_text(*, language: str, context: FastChatContext, links: list[dict], summary: str = "", reused: bool = False) -> str:
    subject = context.reference_target.replace("_", " ").lower() or context.current_subject.replace("_", " ").lower() or context.current_symptom
    if language == "ru":
        intro = "\u041d\u0430\u0448\u0435\u043b \u0432 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u043d\u044b\u0445 \u043c\u0430\u0442\u0435\u0440\u0438\u0430\u043b\u0430\u0445" if reused else "\u041d\u0430\u0448\u0435\u043b \u0440\u0435\u0430\u043b\u044c\u043d\u044b\u0435 \u0441\u0441\u044b\u043b\u043a\u0438"
        lines = [f"{intro} \u043f\u043e \u044d\u0442\u043e\u0439 \u0442\u0435\u043c\u0435: {subject}."]
        if summary:
            lines.append(summary)
        for item in links[:4]:
            title = str(item.get("title") or item.get("url") or "").strip()
            url = str(item.get("url") or "").strip()
            if title and url:
                lines.append(f"{title}: {url}")
        return "\n".join(lines)
    intro = "I found this in saved PULS material" if reused else "I found real reference links"
    lines = [f"{intro} for the same subject: {subject}."]
    if summary:
        lines.append(summary)
    for item in links[:4]:
        title = str(item.get("title") or item.get("url") or "").strip()
        url = str(item.get("url") or "").strip()
        if title and url:
            lines.append(f"{title}: {url}")
    return "\n".join(lines)


def _question_tail(language: str) -> str:
    if language == "ru":
        return "\u042d\u0442\u043e \u043f\u043e\u043c\u043e\u0433\u043b\u043e? \u0415\u0441\u043b\u0438 \u043d\u0435\u0442 - \u043d\u0430\u043f\u0438\u0448\u0438 '\u043d\u0435 \u043f\u043e\u043c\u043e\u0433\u043b\u043e', \u0438 \u044f \u043f\u043e\u0438\u0449\u0443 \u0433\u043b\u0443\u0431\u0436\u0435."
    return "Did this solve the problem? If not, write 'not helped' and I will search deeper."


async def _localize_links(links: list[dict], language: str) -> list[dict]:
    if not links or str(language or "").lower().startswith("en"):
        return links or []
    translated = await translate_segments(
        segments=[str(item.get("title") or "") for item in links],
        target_language=language,
    )
    localized = []
    for item, title in zip(links, translated):
        localized.append({**item, "title": title or item.get("title") or item.get("url") or ""})
    return localized


async def _localize_text_blocks(blocks: list[str], language: str) -> list[str]:
    if not blocks or str(language or "").lower().startswith("en"):
        return blocks
    return await translate_segments(segments=blocks, target_language=language)


def _diagnostic_provider_blocks(result: dict) -> tuple[str, list[str], list[str], list[str], list[dict]] | None:
    if not isinstance(result, dict):
        return None
    structured = result.get("structured") if isinstance(result.get("structured"), dict) else {}
    diagnosis = str(
        structured.get("diagnosis")
        or result.get("answer")
        or result.get("short_conclusion")
        or result.get("most_likely")
        or ""
    ).strip()
    if not diagnosis:
        return None
    causes = [str(item).strip() for item in structured.get("probable_causes") or [] if str(item).strip()]
    if not causes and result.get("most_likely"):
        causes = [str(result.get("most_likely")).strip()]
    if result.get("why"):
        causes.append(str(result.get("why")).strip())
    checks = [str(item).strip() for item in structured.get("first_checks") or result.get("first_checks") or [] if str(item).strip()]
    less = [str(item).strip() for item in structured.get("less_likely") or result.get("less_likely") or [] if str(item).strip()]
    change_notes = [str(item).strip() for item in result.get("what_would_change_diagnosis") or [] if str(item).strip()]
    if change_notes:
        checks.append("What would change diagnosis: " + "; ".join(change_notes))
    links = result.get("links") if isinstance(result.get("links"), list) else result.get("sources") if isinstance(result.get("sources"), list) else []
    return diagnosis, causes, checks, less, links


async def _try_diagnostic_provider_answer(
    *,
    context: dict,
    language: str,
    fallback_links: list[dict],
    question_tail: str,
) -> tuple[str, list[dict]] | None:
    try:
        result = run_diagnostic_provider(context)
    except Exception:
        return None
    blocks = _diagnostic_provider_blocks(result)
    if blocks is None:
        return None
    diagnosis, probable_causes, first_checks, less_likely, provider_links = blocks
    links = provider_links or fallback_links
    localized_blocks = await _localize_text_blocks(
        [diagnosis, *probable_causes, *first_checks, *less_likely],
        language,
    )
    diagnosis = localized_blocks[0] if localized_blocks else diagnosis
    probable_causes = localized_blocks[1 : 1 + len(probable_causes)]
    checks_start = 1 + len(probable_causes)
    first_checks = localized_blocks[checks_start : checks_start + len(first_checks)]
    less_start = checks_start + len(first_checks)
    less_likely = localized_blocks[less_start:]
    localized_links = await _localize_links(links, language)
    return (
        format_technical_answer(
            language=language,
            diagnosis=diagnosis,
            probable_causes=probable_causes[:3],
            first_checks=first_checks[:4],
            less_likely=less_likely[:3],
            links=localized_links,
            question_tail=question_tail,
        ),
        localized_links,
    )


def _build_parser_history_context(history: str, *, symptom: str, active_car: str, max_blocks: int = 2) -> str:
    blocks = [block.strip() for block in str(history or "").split("\n---\n") if block.strip()]
    selected = []
    for block in reversed(blocks):
        lowered = _normalize_phrase(block)
        if active_car and _normalize_phrase(active_car) not in lowered:
            continue
        if symptom and any(part in lowered for part in _normalize_phrase(symptom).split()[:6]):
            selected.append(block)
        if len(selected) >= max_blocks:
            break
    selected.reverse()
    return "\n---\n".join(selected)[:4000]


def _analyze_context(*, normalized, user, decision: RouterDecision, latest_context: dict | None) -> tuple[FastChatContext, object, dict | None]:
    latest_context = latest_context or {}
    text = str(normalized.text or "").strip()
    language = str(decision.language or normalized.language or "en")[:2]
    mentioned_car = _extract_active_car_from_text(text)
    conversation_car = str(latest_context.get("active_car") or "").strip()
    payload_car = str(normalized.car_info or "").strip()
    fallback_car = str(getattr(user, "car_info", "") or "").strip()
    wants_context_or_profile = (
        _looks_like_meta_followup(text, str(latest_context.get("last_assistant_text") or ""))
        or _looks_like_context_capability_question(text)
        or _looks_like_vehicle_profile_question(text)
    )
    previous_reference_target = _latest_reference_target(latest_context)
    explicit_reference = _looks_like_reference_request(text)

    mode = "GENERAL_CHAT"
    if wants_context_or_profile:
        mode = "META_CHAT"
    elif _looks_like_feedback_helped(text, decision):
        mode = "FEEDBACK"
    elif _looks_like_feedback_not_helped(text, decision):
        mode = "FEEDBACK"
    elif explicit_reference:
        mode = "REFERENCE_REQUEST"
    elif _looks_like_source_question(text) or _looks_like_detail_request(text):
        mode = "KNOWLEDGE_REQUEST"
    elif decision.message_type == "general" and not _has_automotive_content(text):
        mode = "GENERAL_CHAT"
    elif mentioned_car and conversation_car and _normalize_phrase(mentioned_car) != _normalize_phrase(conversation_car):
        mode = "VEHICLE_SWITCH"
    elif mentioned_car:
        mode = "AUTOMOTIVE_NEW_CASE"
    elif conversation_car and _has_automotive_content(text):
        mode = "AUTOMOTIVE_CONTINUATION"
    elif _latest_non_social_user_text(latest_context, getattr(user, "conversation_history", "") or "") and _has_automotive_content(text):
        mode = "AUTOMOTIVE_CONTINUATION"
    elif _has_automotive_content(text):
        mode = "AUTOMOTIVE_NEW_CASE"
    elif decision.message_type in {"new_diagnostic", "clarification"} and (decision.active_car or decision.car_info or _has_automotive_content(decision.symptom)):
        mode = "AUTOMOTIVE_NEW_CASE"

    active_car = mentioned_car or conversation_car or payload_car or (
        fallback_car if mode not in {"GENERAL_CHAT", "META_CHAT"} or wants_context_or_profile else ""
    )
    vehicle_id, active_car, resolved_vehicle = _resolve_vehicle(user_id=user.id, car_text=active_car)
    if active_car:
        normalized = normalized.model_copy(update={"car_info": active_car})

    case_seed = _build_case_seed(latest_context, getattr(user, "conversation_history", "") or "", text)
    if mode == "GENERAL_CHAT" and _looks_like_case_related_reply(
        text=text,
        latest_context=latest_context,
        active_car=active_car,
        case_seed=case_seed,
    ):
        mode = "AUTOMOTIVE_CONTINUATION"
    current_symptom = case_seed if mode in {"AUTOMOTIVE_CONTINUATION", "FEEDBACK"} else text
    if mode in {"KNOWLEDGE_REQUEST", "REFERENCE_REQUEST", "META_CHAT"}:
        current_symptom = case_seed or text
    problem_class = _classify_problem(" ".join(part for part in (case_seed, text) if part))
    reference_target = _infer_reference_target(text, previous_reference_target)
    current_subject = reference_target or (problem_class if problem_class != "OTHER" else "")
    search_intent = _classify_search_intent(text, problem_class, current_subject)

    messages = (latest_context or {}).get("recent_messages") or []
    clarification_count = sum(
        1
        for item in messages
        if isinstance(item, dict)
        and str(item.get("role") or "").lower() == "assistant"
        and _assistant_asked_clarification(str(item.get("text") or ""))
    )
    enough = _enough_context_for_knowledge(current_symptom, case_seed)
    if _looks_like_feedback_not_helped(text, decision) or _looks_like_detail_request(text):
        enough = True

    needs_clarification = mode in {"AUTOMOTIVE_NEW_CASE", "AUTOMOTIVE_CONTINUATION"} and search_intent == "DIAGNOSTIC_SEARCH" and not enough
    if clarification_count >= 2 and _contains_case_detail(current_symptom):
        needs_clarification = False

    should_search = mode in {"AUTOMOTIVE_NEW_CASE", "AUTOMOTIVE_CONTINUATION", "VEHICLE_SWITCH", "KNOWLEDGE_REQUEST", "REFERENCE_REQUEST", "FEEDBACK"} and not needs_clarification
    should_deep_search = _looks_like_feedback_not_helped(text, decision) or _looks_like_detail_request(text) or decision.deep_search

    context = FastChatContext(
        mode=mode,
        language=language,
        active_car=active_car,
        vehicle_id=vehicle_id,
        current_symptom=current_symptom,
        previous_symptom=_latest_non_social_user_text(latest_context, getattr(user, "conversation_history", "") or ""),
        problem_class=problem_class,
        search_intent=search_intent,
        current_subject=current_subject,
        reference_target=reference_target,
        case_seed=case_seed,
        user_facts=[text] if mode not in {"GENERAL_CHAT", "META_CHAT"} and text else [],
        evidence_links=[],
        should_search=should_search,
        should_deep_search=should_deep_search,
        needs_clarification=needs_clarification,
    )
    return context, normalized, resolved_vehicle


async def _persist_and_return(
    *,
    user,
    normalized,
    answer_text: str,
    context: FastChatContext,
    message_type: str,
    links: list[dict] | None = None,
    parser_used: bool = False,
    parsed_case: dict | None = None,
    should_decrease_limit: bool = False,
) -> ChatResponse:
    answer_text = _plain_text_response(answer_text)
    await update_user_after_response(
        user,
        normalized,
        answer_text,
        should_decrease_limit=should_decrease_limit,
        active_car=context.active_car,
        symptom=context.current_symptom,
        message_type=message_type,
        links=links or [],
        parser_used=parser_used,
        deep_search_used=bool(parser_used and context.should_deep_search),
        vehicle_id=context.vehicle_id,
        parsed_case=parsed_case,
        force_new_conversation=context.mode == "VEHICLE_SWITCH",
    )
    return ChatResponse(answer=answer_text, links=links or [], quota=_quota_payload(user))


async def process_chat_message(payload: dict, source: str) -> ChatResponse:
    normalized = normalize_chat_input(payload, source=source)
    user = await get_or_create_user(normalized)
    latest_context = get_latest_conversation_context(user_id=user.id)
    decision = await route_message(normalized, user)
    context, normalized, resolved_vehicle = _analyze_context(
        normalized=normalized,
        user=user,
        decision=decision,
        latest_context=latest_context,
    )

    if context.mode in {"GENERAL_CHAT", "META_CHAT"}:
        preserved_car = str((latest_context or {}).get("active_car") or "").strip()
        if preserved_car:
            vehicle_id, preserved_car, _ = _resolve_vehicle(user_id=user.id, car_text=preserved_car)
            context.active_car = preserved_car
            context.vehicle_id = vehicle_id
            context.current_symptom = _latest_non_social_user_text(latest_context, getattr(user, "conversation_history", "") or "")
        if context.mode == "META_CHAT":
            fallback = _meta_conversation_text(
                language=context.language,
                user_text=normalized.text,
                previous_assistant=str((latest_context or {}).get("last_assistant_text") or ""),
                active_car=context.active_car,
            )
            answer_text = await _natural_chat_text(
                mode="META_CHAT",
                context=context,
                normalized=normalized,
                latest_context=latest_context,
                fallback=fallback,
            )
        else:
            fallback = _general_conversation_text(context.language, decision.response, normalized.text)
            answer_text = await _natural_chat_text(
                mode="GENERAL_CHAT",
                context=context,
                normalized=normalized,
                latest_context=latest_context,
                assistant_hint=decision.response,
                fallback=fallback,
            )
        return await _persist_and_return(
            user=user,
            normalized=normalized,
            answer_text=answer_text,
            context=context,
            message_type="general",
        )

    if _looks_like_source_question(normalized.text):
        stored = _stored_evidence_answer(language=context.language, history=getattr(user, "conversation_history", "") or "")
        if stored is not None:
            answer_text, links = stored
            localized_links = await _localize_links(links, context.language)
            return await _persist_and_return(
                user=user,
                normalized=normalized,
                answer_text=answer_text,
                context=context,
                message_type="general",
                links=localized_links,
            )

    if context.search_intent in {"REFERENCE_SEARCH", "MANUAL_SEARCH", "IMAGE_REFERENCE", "VIDEO_REFERENCE"}:
        reusable_links = find_reusable_media(
            user_id=user.id,
            vehicle_id=context.vehicle_id,
            subject=" ".join(
                part
                for part in (context.active_car, context.reference_target, context.current_subject, context.current_symptom)
                if part
            ),
            intent=context.search_intent,
        )
        if reusable_links:
            answer_text = _reference_answer_text(
                language=context.language,
                context=context,
                links=reusable_links,
                reused=True,
            )
            return await _persist_and_return(
                user=user,
                normalized=normalized,
                answer_text=answer_text,
                context=context,
                message_type="general",
                links=reusable_links,
            )
        try:
            reference_result = await search_reference(
                active_vehicle=context.active_car,
                current_subject=context.current_subject or context.current_symptom,
                reference_target=context.reference_target,
                user_text=normalized.text,
                language=context.language,
                intent=context.search_intent,
            )
            links = await _localize_links(reference_result.get("links") or [], context.language)
            upsert_reference_media(
                user_id=user.id,
                vehicle=resolved_vehicle,
                links=links,
                subject=context.current_subject or context.current_symptom,
                reference_target=context.reference_target,
                language=context.language,
            )
            answer_text = _reference_answer_text(
                language=context.language,
                context=context,
                links=links,
                summary=str(reference_result.get("summary") or ""),
                reused=False,
            )
            return await _persist_and_return(
                user=user,
                normalized=normalized,
                answer_text=answer_text,
                context=context,
                message_type="kb_match",
                links=links,
                parsed_case={"reference_search": reference_result.get("raw") or {}, "links": links},
                should_decrease_limit=False,
            )
        except ReferenceSearchUnavailableError:
            answer_text = (
                "\u041f\u043e\u043d\u044f\u043b \u0442\u0435\u043c\u0443, \u043d\u043e \u043f\u043e\u043a\u0430 \u043d\u0435 \u043d\u0430\u0448\u0435\u043b \u0434\u043e\u0441\u0442\u0430\u0442\u043e\u0447\u043d\u043e \u043d\u0430\u0434\u0435\u0436\u043d\u044b\u0445 \u0441\u0441\u044b\u043b\u043e\u043a. \u041c\u043e\u0433\u0443 \u043f\u0440\u043e\u0434\u043e\u043b\u0436\u0438\u0442\u044c, \u0435\u0441\u043b\u0438 \u0443\u0442\u043e\u0447\u043d\u0438\u0448\u044c \u043a\u0443\u0437\u043e\u0432, \u0434\u0432\u0438\u0433\u0430\u0442\u0435\u043b\u044c \u0438\u043b\u0438 \u043d\u0443\u0436\u043d\u044b\u0439 \u0443\u0437\u0435\u043b."
                if context.language == "ru"
                else "I understand the subject, but I did not find a reliable reusable link yet. A body, engine, or component detail would narrow it down."
            )
            return await _persist_and_return(
                user=user,
                normalized=normalized,
                answer_text=answer_text,
                context=context,
                message_type="clarification",
            )

    if _looks_like_feedback_helped(normalized.text, decision):
        feedback_state = context
        matched_feedback_case = await find_latest_case_for_feedback(feedback_state)
        if matched_feedback_case is not None:
            await increment_case_success(
                matched_feedback_case.get("id"),
                source_table=str(matched_feedback_case.get("source_table") or "knowledge_cases"),
            )
        answer_text = (
            "\u041e\u0442\u043b\u0438\u0447\u043d\u043e, \u0440\u0430\u0434 \u0447\u0442\u043e \u043f\u043e\u043c\u043e\u0433\u043b\u043e. \u0421\u043e\u0445\u0440\u0430\u043d\u044e \u044d\u0442\u043e \u043a\u0430\u043a \u0443\u0441\u043f\u0435\u0448\u043d\u044b\u0439 \u043a\u0435\u0439\u0441."
            if context.language == "ru"
            else "Great, glad it helped. I will keep this with the current case."
        )
        return await _persist_and_return(
            user=user,
            normalized=normalized,
            answer_text=answer_text,
            context=context,
            message_type="feedback_helped",
        )

    if context.needs_clarification:
        stage = 2 if _contains_case_detail(context.current_symptom) else 1
        fallback = _clarification_text(
            language=context.language,
            active_car=context.active_car,
            symptom=context.current_symptom,
            problem_class=context.problem_class,
            stage=stage,
        )
        answer_text = await _natural_chat_text(
            mode="CLARIFICATION",
            context=context,
            normalized=normalized,
            latest_context=latest_context,
            fallback=fallback,
        )
        return await _persist_and_return(
            user=user,
            normalized=normalized,
            answer_text=answer_text,
            context=context,
            message_type="clarification",
        )

    matched_case = None
    if context.should_search and not context.should_deep_search:
        matched_case = await find_matching_case(context, decision)
        if not matched_case and getattr(user, "conversation_history", ""):
            matched_case = await find_matching_history_case(
                history=user.conversation_history,
                active_car=context.active_car,
                symptom=context.current_symptom,
                language=context.language,
            )

    if matched_case and (matched_case.get("answer") or matched_case.get("links")):
        answer, embedded_links = _clean_case_answer(str(matched_case.get("answer") or ""))
        links = matched_case.get("links") or embedded_links or []
        diagnostic_context = build_diagnostic_context(
            state=context,
            normalized=normalized,
            user=user,
            resolved_vehicle=resolved_vehicle,
            latest_context=latest_context,
            effective_symptom=context.current_symptom,
            diagnosis_text=answer,
            response_links=links,
            internal_match={**matched_case, "answer": answer, "links": links},
            internal_match_kind="history" if matched_case.get("source_type") == "history" else "kb",
        )
        provider_answer = await _try_diagnostic_provider_answer(
            context=diagnostic_context,
            language=context.language,
            fallback_links=links,
            question_tail=_question_tail(context.language),
        )
        if provider_answer is not None:
            answer_text, links = provider_answer
        else:
            localized_answer = (await _localize_text_blocks([answer], context.language))[0]
            links = await _localize_links(links, context.language)
            answer_text = format_from_kb(
                language=context.language,
                answer=localized_answer,
                links=links,
                question_tail=_question_tail(context.language),
            )
        return await _persist_and_return(
            user=user,
            normalized=normalized,
            answer_text=answer_text,
            context=context,
            message_type="kb_match",
            links=links,
        )

    if context.should_search:
        can_run, subscription = can_run_parser(user_id=user.id)
        if not can_run:
            answer_text = (
                "\u041b\u0438\u043c\u0438\u0442 \u0437\u0430\u043f\u0440\u043e\u0441\u043e\u0432 PULS \u0437\u0430\u043a\u043e\u043d\u0447\u0438\u043b\u0441\u044f. \u041d\u0443\u0436\u0435\u043d \u043f\u043b\u0430\u0442\u043d\u044b\u0439 \u0442\u0430\u0440\u0438\u0444, \u0447\u0442\u043e\u0431\u044b \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c Parser \u0438\u043b\u0438 Deep Search."
                if context.language == "ru"
                else "Your PULS request limit is exhausted. A paid plan is required to run Parser or Deep Search."
            )
            await update_user_after_response(
                user,
                normalized,
                answer_text,
                should_decrease_limit=False,
                active_car=context.active_car,
                symptom=context.current_symptom,
                message_type="limit",
                vehicle_id=context.vehicle_id,
            )
            return ChatResponse(answer=answer_text, links=[], quota=quota_payload(subscription))

        parser_history = _build_parser_history_context(
            getattr(user, "conversation_history", "") or "",
            symptom=context.current_symptom,
            active_car=context.active_car,
        )
        try:
            parsed_case = await parse_diagnostic(
                {
                    "active_car": context.active_car,
                    "symptom": context.current_symptom,
                    "query": context.current_symptom,
                    "conversation_history": parser_history,
                    "deep_search": bool(context.should_deep_search),
                    "language": context.language,
                }
            )
        except ParserUnavailableError:
            answer_text = _fallback_diagnostic_text(
                language=context.language,
                active_car=context.active_car,
                symptom=context.current_symptom,
            )
            return await _persist_and_return(
                user=user,
                normalized=normalized,
                answer_text=answer_text,
                context=context,
                message_type="parser_fallback",
                parser_used=True,
            )

        diagnosis_text = str(parsed_case.get("parser_summary") or "").strip()
        extracted_cases = parsed_case.get("extracted_cases") or []
        probable_causes = [str(case.get("cause") or "").strip() for case in extracted_cases if isinstance(case, dict) and case.get("cause")]
        first_checks = [str(case.get("solution") or "").strip() for case in extracted_cases if isinstance(case, dict) and case.get("solution")]
        less_likely = probable_causes[3:]
        probable_causes = probable_causes[:3]
        answer_context = "\n".join([diagnosis_text, *probable_causes, *first_checks, *less_likely])
        response_links = filter_response_sources(
            current_query=context.current_symptom,
            effective_symptom=context.current_symptom,
            answer_context=answer_context,
            links=parsed_case.get("links") or [],
            extracted_cases=extracted_cases,
        )
        diagnostic_context = build_diagnostic_context(
            state=context,
            normalized=normalized,
            user=user,
            resolved_vehicle=resolved_vehicle,
            latest_context=latest_context,
            effective_symptom=context.current_symptom,
            parser_query=context.current_symptom,
            parser_history=parser_history,
            parsed_case=parsed_case,
            diagnosis_text=diagnosis_text,
            probable_causes=probable_causes,
            first_checks=first_checks,
            less_likely=less_likely,
            response_links=response_links,
        )
        provider_answer = await _try_diagnostic_provider_answer(
            context=diagnostic_context,
            language=context.language,
            fallback_links=response_links,
            question_tail=_question_tail(context.language),
        )
        if provider_answer is not None:
            answer_text, response_links = provider_answer
        elif diagnosis_text or probable_causes or first_checks:
            localized_blocks = await _localize_text_blocks(
                [diagnosis_text, *probable_causes, *first_checks, *less_likely],
                context.language,
            )
            diagnosis = localized_blocks[0] if localized_blocks else diagnosis_text
            cause_end = 1 + len(probable_causes)
            check_end = cause_end + len(first_checks)
            localized_links = await _localize_links(response_links, context.language)
            answer_text = format_technical_answer(
                language=context.language,
                diagnosis=diagnosis,
                probable_causes=localized_blocks[1:cause_end],
                first_checks=localized_blocks[cause_end:check_end][:4],
                less_likely=localized_blocks[check_end:][:3],
                links=localized_links,
                question_tail=_question_tail(context.language),
            )
            response_links = localized_links
        else:
            answer_text = _fallback_diagnostic_text(
                language=context.language,
                active_car=context.active_car,
                symptom=context.current_symptom,
            )

        return await _persist_and_return(
            user=user,
            normalized=normalized,
            answer_text=answer_text,
            context=context,
            message_type="parser",
            links=response_links,
            parser_used=True,
            parsed_case=parsed_case,
            should_decrease_limit=True,
        )

    fallback = _clarification_text(
        language=context.language,
        active_car=context.active_car,
        symptom=context.current_symptom,
        problem_class=context.problem_class,
    )
    answer_text = await _natural_chat_text(
        mode="CLARIFICATION",
        context=context,
        normalized=normalized,
        latest_context=latest_context,
        fallback=fallback,
    )
    return await _persist_and_return(
        user=user,
        normalized=normalized,
        answer_text=answer_text,
        context=context,
        message_type="clarification",
    )
