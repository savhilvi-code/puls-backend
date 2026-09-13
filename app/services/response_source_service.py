from __future__ import annotations

import re
from typing import Any


_ENGINE_OIL_QUERY_TERMS = (
    "engine oil",
    "motor oil",
    "oil for engine",
    "oil in engine",
    "моторное масло",
    "масло в двигатель",
    "масло для двигателя",
    "масло двс",
    "масло для двс",
)

_ENGINE_OIL_LINK_TERMS = (
    "engine oil",
    "motor oil",
    "моторное масло",
    "вязкость",
    "viscosity",
    "oil grade",
    "oil specification",
    "oil spec",
    "oil capacity",
    "объем масла",
    "объём масла",
    "oil change",
    "замена масла",
    "oil filter",
    "масляный фильтр",
    "5w",
    "10w",
    "sae",
    "api sn",
    "ilsac",
)

_ENGINE_OIL_NEGATIVE_TERMS = (
    "atf",
    "акпп",
    "automatic transmission",
    "transmission oil",
    "gearbox oil",
    "трансмиссион",
    "коробк",
    "кпп",
    "cvt",
    "вариатор",
    "transfer case",
    "раздат",
    "diff oil",
    "differential oil",
    "ремень",
    "ремни",
    "belt",
    "belts",
    "грм",
    "подвеск",
    "suspension",
    "brake",
    "тормоз",
)

_ENGINE_SPECIFIC_TERMS = (
    "engine oil",
    "motor oil",
    "моторное масло",
    "двигател",
    "двс",
)

_VALVE_SEAL_TERMS = (
    "маслосъем",
    "маслосъём",
    "valve stem",
    "valve seal",
)

_OIL_CONSUMPTION_TERMS = (
    "oil consumption",
    "oil burning",
    "burns oil",
    "расход масла",
    "жрет масло",
    "жрёт масло",
    "ест масло",
    "угар масла",
)


def _normalize_text(value: Any) -> str:
    text = str(value or "").casefold()
    text = text.replace("ё", "е")
    return re.sub(r"\s+", " ", text).strip()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _link_blob(link: dict[str, Any]) -> str:
    return _normalize_text(
        " ".join(
            str(link.get(key) or "")
            for key in ("title", "url", "description", "type", "source", "forum", "key_info")
        )
    )


def _detect_topic(*, current_query: str, effective_symptom: str) -> str:
    text = _normalize_text(f"{current_query} {effective_symptom}")
    if _contains_any(text, _ENGINE_OIL_QUERY_TERMS):
        return "ENGINE_OIL"
    if "какое масло" in text and _contains_any(text, ("двигател", "двс", "engine")):
        return "ENGINE_OIL"
    return ""


def _has_oil_consumption_context(*, current_query: str, effective_symptom: str, answer_context: str) -> bool:
    text = _normalize_text(f"{current_query} {effective_symptom} {answer_context}")
    return _contains_any(text, _OIL_CONSUMPTION_TERMS)


def _is_engine_oil_link(blob: str, *, oil_consumption_context: bool) -> bool:
    if _contains_any(blob, _VALVE_SEAL_TERMS):
        return oil_consumption_context

    has_positive = _contains_any(blob, _ENGINE_OIL_LINK_TERMS)
    if not has_positive:
        return False

    has_negative = _contains_any(blob, _ENGINE_OIL_NEGATIVE_TERMS)
    has_engine_specific = _contains_any(blob, _ENGINE_SPECIFIC_TERMS)
    if has_negative and not has_engine_specific:
        return False

    return True


def filter_response_sources(
    *,
    current_query: str,
    effective_symptom: str,
    answer_context: str,
    links: list[dict] | None,
    extracted_cases: list[dict] | None,
) -> list[dict]:
    """Return user-facing sources without mutating parser discovery evidence."""
    source_links = list(links or [])
    topic = _detect_topic(current_query=current_query, effective_symptom=effective_symptom)
    if topic != "ENGINE_OIL":
        return source_links

    oil_consumption_context = _has_oil_consumption_context(
        current_query=current_query,
        effective_symptom=effective_symptom,
        answer_context=answer_context,
    )
    filtered = [
        link
        for link in source_links
        if isinstance(link, dict)
        and _is_engine_oil_link(_link_blob(link), oil_consumption_context=oil_consumption_context)
    ]

    # Conservative fallback: if all links would disappear, preserve current behavior.
    return filtered or source_links
