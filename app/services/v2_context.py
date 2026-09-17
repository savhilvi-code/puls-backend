from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


BRAND_PATTERN = re.compile(
    r"\b(toyota|lexus|nissan|infiniti|honda|acura|mazda|subaru|mitsubishi|suzuki|"
    r"bmw|mercedes(?:-benz)?|audi|volkswagen|vw|porsche|opel|skoda|renault|peugeot|"
    r"citroen|fiat|volvo|ford|chevrolet|cadillac|dodge|jeep|chrysler|ram|hyundai|kia|"
    r"genesis|lada)\b(?:\s+[A-Za-z0-9.-]+){0,7}",
    re.IGNORECASE,
)

ENGINE_PATTERN = re.compile(
    r"\b(?:[1-9][.,]\d\s?(?:l|liter)|v[68]|i[46]|sr20vet|sr20|qr20|qr25|vq35|"
    r"1zz|2zz|2gr|1gr|1g[- ]?gze|1ggze|ej20|ej25|fa20|fb25|k20|k24|m54|m57|"
    r"n52|n54|n55|b58)\b",
    re.IGNORECASE,
)

DTC_PATTERN = re.compile(
    r"\b[pucb]\d{4}\b",
    re.IGNORECASE,
)

AUTOMOTIVE_TERMS = (
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
    "машин",
    "автомоб",
    "двигат",
    "мотор",
    "холост",
    "оборот",
    "вибрац",
    "троит",
    "не тянет",
    "разгон",
    "нагруз",
    "холод",
    "горяч",
    "прогрев",
    "после",
    "замен",
    "ошиб",
    "чек",
    "стук",
    "шум",
    "масло",
    "жидк",
    "завод",
    "стартер",
    "акпп",
    "коробк",
    "вариатор",
    "тормоз",
)


@dataclass
class TurnContext:
    mode: str
    language: str
    text: str
    vehicle: dict[str, Any] | None = None
    problem: dict[str, Any] | None = None
    current_subject: str = ""
    symptom: str = ""
    problem_class: str = "OTHER"
    clarification_question: str = ""
    needs_research: bool = False
    technical_facts: list[dict[str, Any]] = field(
        default_factory=list
    )


def normalize_phrase(text: str) -> str:
    return " ".join(
        str(text or "").lower().split()
    )


def word_count(text: str) -> int:
    return len(
        [
            part
            for part in re.split(
                r"\s+",
                str(text or "").strip(),
            )
            if part
        ]
    )


def contains_any(
    text: str,
    terms: tuple[str, ...],
) -> bool:
    lowered = normalize_phrase(text)
    return any(
        term in lowered
        for term in terms
    )


def plain_text_response(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(
        r"(?m)^\s{0,3}#{1,6}\s*",
        "",
        cleaned,
    )
    cleaned = cleaned.replace(
        "**",
        "",
    ).replace(
        "__",
        "",
    )
    cleaned = re.sub(
        r"(?m)^\s*[-*]\s+",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"\n{3,}",
        "\n\n",
        cleaned,
    )
    return cleaned.strip()


def vehicle_label(
    vehicle: dict[str, Any] | None,
) -> str:
    """
    Canonical Supabase V2 vehicle label.

    vehicles:
      make
      model
      generation
      year
      engine_code

    Do not use legacy brand / engine fields.
    """
    vehicle = vehicle or {}

    parts = [
        vehicle.get("make"),
        vehicle.get("model"),
        vehicle.get("generation"),
        vehicle.get("year"),
        vehicle.get("engine_code"),
    ]

    return " ".join(
        str(part).strip()
        for part in parts
        if str(part or "").strip()
    ).strip()


def extract_vehicle_label(text: str) -> str:
    """
    Extract a vehicle mention from free text.

    This identifies a mention only. It does NOT create a vehicle
    and does NOT imply ownership by the user.
    """
    raw = " ".join(
        str(text or "")
        .replace(",", " ")
        .split()
    )

    match = BRAND_PATTERN.search(raw)

    if not match:
        return ""

    label = match.group(0).strip(
        " .,:;!?"
    )

    year = re.search(
        r"\b(19[8-9]\d|20[0-3]\d)\b",
        raw,
    )

    engine = ENGINE_PATTERN.search(raw)

    if (
        year
        and year.group(0) not in label
    ):
        label = (
            f"{label} {year.group(0)}"
        )

    if (
        engine
        and engine.group(0).lower()
        not in label.lower()
    ):
        label = (
            f"{label} {engine.group(0)}"
        )

    return label


def has_automotive_content(text: str) -> bool:
    """
    Lightweight routing signal only.

    Automotive content can be detected by:
    - explicit vehicle mention;
    - DTC;
    - automotive terminology.

    This function must not create diagnostic artifacts.
    """
    raw = str(text or "")

    return bool(
        extract_vehicle_label(raw)
        or DTC_PATTERN.search(raw)
        or contains_any(
            raw,
            AUTOMOTIVE_TERMS,
        )
    )


def is_social_general_text(text: str) -> bool:
    """
    Detect short social/general phrases.

    Automotive content always wins over this heuristic.
    """
    lowered = normalize_phrase(
        text
    ).strip(
        " .,:;!?"
    )

    if (
        not lowered
        or has_automotive_content(
            lowered
        )
    ):
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
        "привет",
        "как дела",
        "как ты",
        "спасибо",
        "ок",
        "окей",
    )

    return (
        word_count(lowered) <= 6
        and any(
            term in lowered
            for term in social_terms
        )
    )


def looks_like_meta_question(text: str) -> bool:
    lowered = normalize_phrase(text)

    return contains_any(
        lowered,
        (
            "remember",
            "memory",
            "context",
            "previous chat",
            "conversation",
            "what you said",
            "what do you mean",
            "what car do i have",
            "do you know my car",
            "помн",
            "контекст",
            "переписк",
            "что ты сказал",
            "что ты имеешь",
            "какая у меня машина",
            "знаешь мою машину",
        ),
    )


def is_reference_request(text: str) -> bool:
    """Return True for vehicle HOWTO/reference requests, not fault reports."""
    lowered = normalize_phrase(text)
    request_markers = (
        "youtube", "ютуб", "видео", "video", "manual", "мануал",
        "инструкц", "ссылк", "link", "схем", "diagram", "photo", "фото",
        "как заменить", "как поменять", "как снять", "как установить",
        "how to replace", "how to change", "how to remove", "how to install",
        "где находится", "where is", "расположение", "location",
        "какое масло", "какую жидкость", "what oil", "which oil",
        "спецификац", "допуск масла", "oil specification",
    )
    return any(marker in lowered for marker in request_markers)


def is_factual_technical_statement(text: str) -> bool:
    """Accept only user statements that establish a vehicle technical fact."""
    source = str(text or "").strip()
    lowered = normalize_phrase(source)
    if (
        not source
        or is_social_general_text(source)
        or looks_like_meta_question(source)
        or is_reference_request(source)
    ):
        return False
    if DTC_PATTERN.search(source):
        return True
    factual_markers = (
        "не завод", "не запуск", "не едет", "не трог", "не тянет",
        "глох", "троит", "вибрац", "стук", "шум", "гул", "теч",
        "перегре", "горит", "ошиб", "чек", "рыв", "пина", "букс",
        "слом", "заменил", "заменили", "поменял", "отремонт", "не может",
        "переста", "только на холод", "только на горяч",
        "does not", "doesn't", "won't", "stalls", "misfire", "vibrat",
        "noise", "knock", "leak", "overheat", "warning", "replaced",
        "repaired", "problem with", "проблема с",
    )
    return any(marker in lowered for marker in factual_markers)


def classify_problem(text: str) -> str:
    lowered = normalize_phrase(text)

    classes = (
        (
            "NO_START",
            (
                "no start",
                "won't start",
                "does not start",
                "no crank",
                "не заводится",
                "не завод",
                "не запускается",
                "не запуск",
                "стартер не крут",
            ),
        ),
        (
            "HARD_START",
            (
                "hard start",
                "starts badly",
                "hard to start",
                "плохо завод",
                "плохо запуска",
                "долго завод",
                "долго запуска",
                "трудно завод",
            ),
        ),
        (
            "STALL",
            (
                "stall",
                "stalls",
                "глох",
                "заглох",
            ),
        ),
        (
            "MISFIRE",
            (
                "misfire",
                "troits",
                "троит",
                "пропуск",
            ),
        ),
        (
            "VIBRATION",
            (
                "vibration",
                "vibrates",
                "вибрац",
            ),
        ),
        (
            "NOISE",
            (
                "noise",
                "knock",
                "rattle",
                "hum",
                "шум",
                "стук",
                "гул",
            ),
        ),
        (
            "POWER_LOSS",
            (
                "power loss",
                "no power",
                "doesn't pull",
                "under load",
                "не тянет",
                "потеря тяг",
                "нагруз",
            ),
        ),
        (
            "OVERHEATING",
            (
                "overheat",
                "temperature",
                "перегре",
                "температур",
            ),
        ),
        (
            "WARNING_DTC",
            (
                "dtc",
                "obd",
                "check engine",
                "ошиб",
                "чек",
            ),
        ),
        (
            "TRANSMISSION",
            (
                "transmission",
                "gearbox",
                "cvt",
                "atf",
                "коробк",
                "акпп",
                "вариатор",
            ),
        ),
        (
            "SERVICE_REFERENCE",
            (
                "oil",
                "fluid",
                "coolant",
                "service",
                "масло",
                "жидк",
                "антифриз",
                "сервис",
            ),
        ),
    )

    for label, terms in classes:
        if any(
            term in lowered
            for term in terms
        ):
            return label

    return "OTHER"


def symptom_has_operating_detail(
    text: str,
) -> bool:
    lowered = normalize_phrase(text)

    if DTC_PATTERN.search(
        str(text or "")
    ):
        return True

    detail_terms = (
        "cold",
        "hot",
        "warm",
        "idle",
        "under load",
        "acceleration",
        "after",
        "only when",
        "когда",
        "на холод",
        "на горяч",
        "после",
        "при разгоне",
        "под нагруз",
        "на холост",
    )

    return any(
        term in lowered
        for term in detail_terms
    )


def clarification_for(
    language: str,
    *,
    missing: str,
    problem_class: str = "OTHER",
) -> str:
    ru = str(
        language or ""
    ).lower().startswith(
        "ru"
    )

    if missing == "vehicle":
        return (
            "По какой именно машине это происходит?"
            if ru
            else "Which vehicle is this happening on?"
        )

    if problem_class == "NO_START":
        return (
            "Уточни один момент: стартер крутит двигатель или вообще нет прокрутки?"
            if ru
            else "One key detail: does the starter crank the engine, or is there no crank at all?"
        )

    if problem_class == "HARD_START":
        return (
            "Уточни, пожалуйста: стартер крутит нормально, но двигатель запускается долго, или стартер тоже крутит медленно?"
            if ru
            else "Please clarify: does the starter crank normally but the engine takes a long time to start, or is the starter itself cranking slowly?"
        )

    if problem_class == "NOISE":
        return (
            "Где слышен шум и когда он появляется: на холостых, при разгоне, на кочках или при торможении?"
            if ru
            else "Where is the noise coming from, and when does it happen: idle, acceleration, bumps, or braking?"
        )

    return (
        "Когда именно проявляется симптом: на холодную, на горячую, на холостых или под нагрузкой?"
        if ru
        else "When exactly does it happen: cold, hot, at idle, or under load?"
    )


def extract_technical_events(
    text: str,
    *,
    answer: str = "",
) -> list[dict[str, Any]]:
    """
    Convert confirmed information from the current turn into canonical
    vehicle_events payloads.

    Supabase V2 vehicle_events fields used here:
      event_type
      title
      details
      source_kind

    Ownership fields (vehicle_id/problem_id) and event_date are added
    by v2_repository.create_vehicle_event().
    """
    source = str(
        text or ""
    ).strip()

    if (
        not source
        or is_social_general_text(
            source
        )
        or looks_like_meta_question(
            source
        )
    ):
        return []

    events: list[
        dict[str, Any]
    ] = []

    codes = sorted(
        {
            match.group(0).upper()
            for match in DTC_PATTERN.finditer(
                source
            )
        }
    )

    for code in codes:
        events.append(
            {
                "event_type": "DTC",
                "title": code,
                "details": {
                    "code": code,
                    "source_text": source,
                },
                "source_kind": "USER",
            }
        )

    if is_factual_technical_statement(source):
        events.append(
            {
                "event_type": "SYMPTOM",
                "title": classify_problem(
                    source
                ),
                "details": {
                    "source_text": source[:500],
                },
                "source_kind": "USER",
            }
        )

    return events
