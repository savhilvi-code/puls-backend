from __future__ import annotations

import re

from app.schemas.parser import DiagnosticRequest
from app.services.parser_engine import diagnose, extract_json


class ParserUnavailableError(RuntimeError):
    pass


_FOCUS_TERM_GROUPS: dict[str, tuple[str, ...]] = {
    "turbo": (
        "турбин",
        "turbo",
        "boost",
        "wastegate",
        "вестгейт",
        "наддув",
        "actuator",
        "актуатор",
        "boost controller",
        "буст контрол",
        "solenoid",
        "соленоид",
    ),
    "airflow": (
        "maf",
        "afm",
        "vaf",
        "дмрв",
        "расходомер",
        "air flow meter",
        "mass air flow",
    ),
    "injector": (
        "форсунк",
        "injector",
        "injectors",
    ),
    "throttle": (
        "дросс",
        "throttle",
        "idle air",
        "iac",
    ),
}

_META_SEARCH_PHRASES = (
    "начинаю глубокий поиск",
    "сначала локализую симптом",
    "ищу реальные темы",
    "нашел реальные темы",
    "нашёл реальные темы",
    "теперь у меня достаточно информации",
    "проанализирую найденное",
    "дополню последним поиском",
    "short diagnosis: understood",
    "starting deep search",
    "first i will localize",
    "looking for real topics",
    "**ru**",
    "**en**",
    "**jp**",
    "**eu**",
)

_UNRELATED_TERM_GROUPS: dict[str, tuple[str, ...]] = {
    "turbo": (
        "подвеск",
        "suspension",
        "трансмис",
        "transmission",
        "выхлоп",
        "exhaust noise",
        "coolant temperature sensor",
        "датчик температуры охлаждающей жидкости",
        "дтож",
        "misfire",
        "пропуск",
    ),
}

_FOCUS_TERM_GROUPS = {
    "turbo": (
        "\u0442\u0443\u0440\u0431\u0438\u043d",
        "turbo",
        "boost",
        "wastegate",
        "\u0432\u0435\u0441\u0442\u0433\u0435\u0439\u0442",
        "\u043d\u0430\u0434\u0434\u0443\u0432",
        "actuator",
        "\u0430\u043a\u0442\u0443\u0430\u0442\u043e\u0440",
        "boost controller",
        "\u0431\u0443\u0441\u0442 \u043a\u043e\u043d\u0442\u0440\u043e\u043b",
        "solenoid",
        "\u0441\u043e\u043b\u0435\u043d\u043e\u0438\u0434",
    ),
    "airflow": (
        "maf",
        "afm",
        "vaf",
        "\u0434\u043c\u0440\u0432",
        "\u0440\u0430\u0441\u0445\u043e\u0434\u043e\u043c\u0435\u0440",
        "air flow meter",
        "mass air flow",
    ),
    "injector": (
        "\u0444\u043e\u0440\u0441\u0443\u043d\u043a",
        "injector",
        "injectors",
    ),
    "throttle": (
        "\u0434\u0440\u043e\u0441\u0441",
        "throttle",
        "idle air",
        "iac",
    ),
}

_META_SEARCH_PHRASES = (
    "\u043d\u0430\u0447\u0438\u043d\u0430\u044e \u0433\u043b\u0443\u0431\u043e\u043a\u0438\u0439 \u043f\u043e\u0438\u0441\u043a",
    "\u0441\u043d\u0430\u0447\u0430\u043b\u0430 \u043b\u043e\u043a\u0430\u043b\u0438\u0437\u0443\u044e \u0441\u0438\u043c\u043f\u0442\u043e\u043c",
    "\u0438\u0449\u0443 \u0440\u0435\u0430\u043b\u044c\u043d\u044b\u0435 \u0442\u0435\u043c\u044b",
    "\u043d\u0430\u0448\u0435\u043b \u0440\u0435\u0430\u043b\u044c\u043d\u044b\u0435 \u0442\u0435\u043c\u044b",
    "\u043d\u0430\u0448\u0451\u043b \u0440\u0435\u0430\u043b\u044c\u043d\u044b\u0435 \u0442\u0435\u043c\u044b",
    "\u0442\u0435\u043f\u0435\u0440\u044c \u0443 \u043c\u0435\u043d\u044f \u0434\u043e\u0441\u0442\u0430\u0442\u043e\u0447\u043d\u043e \u0438\u043d\u0444\u043e\u0440\u043c\u0430\u0446\u0438\u0438",
    "\u043f\u0440\u043e\u0430\u043d\u0430\u043b\u0438\u0437\u0438\u0440\u0443\u044e \u043d\u0430\u0439\u0434\u0435\u043d\u043d\u043e\u0435",
    "\u0434\u043e\u043f\u043e\u043b\u043d\u044e \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u043c \u043f\u043e\u0438\u0441\u043a\u043e\u043c",
    "short diagnosis: understood",
    "starting deep search",
    "first i will localize",
    "looking for real topics",
    "**ru**",
    "**en**",
    "**jp**",
    "**eu**",
)

_UNRELATED_TERM_GROUPS = {
    "turbo": (
        "\u043f\u043e\u0434\u0432\u0435\u0441\u043a",
        "suspension",
        "\u0442\u0440\u0430\u043d\u0441\u043c\u0438\u0441",
        "transmission",
        "\u0432\u044b\u0445\u043b\u043e\u043f",
        "exhaust noise",
        "coolant temperature sensor",
        "\u0434\u0430\u0442\u0447\u0438\u043a \u0442\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u044b \u043e\u0445\u043b\u0430\u0436\u0434\u0430\u044e\u0449\u0435\u0439 \u0436\u0438\u0434\u043a\u043e\u0441\u0442\u0438",
        "\u0434\u0442\u043e\u0436",
        "misfire",
        "\u043f\u0440\u043e\u043f\u0443\u0441\u043a",
    ),
}


def _normalize_links(raw_links) -> list[dict]:
    if not isinstance(raw_links, list):
        return []
    normalized = []
    for item in raw_links:
        if isinstance(item, dict):
            normalized.append(
                {
                    "title": str(item.get("title") or item.get("forum") or item.get("name") or ""),
                    "url": str(item.get("url") or item.get("link") or ""),
                    "description": str(item.get("description") or item.get("key_info") or ""),
                    "type": str(item.get("type") or "link"),
                }
            )
    return normalized


def _normalize_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def _extract_focus_group(query: str) -> str:
    lowered = _normalize_text(query)
    action_markers = (
        "как",
        "настро",
        "регулиров",
        "тюн",
        "tune",
        "adjust",
        "setup",
        "set up",
        "calibrat",
    )
    if not any(marker in lowered for marker in action_markers):
        return ""
    for group, terms in _FOCUS_TERM_GROUPS.items():
        if any(term in lowered for term in terms):
            return group
    return ""


def _extract_focus_group_safe(query: str) -> str:
    lowered = _normalize_text(query)
    action_markers = (
        "\u043a\u0430\u043a",
        "\u043d\u0430\u0441\u0442\u0440\u043e",
        "\u0440\u0435\u0433\u0443\u043b\u0438\u0440\u043e\u0432",
        "\u0442\u044e\u043d",
        "tune",
        "adjust",
        "setup",
        "set up",
        "calibrat",
    )
    if not any(marker in lowered for marker in action_markers):
        return ""
    for group, terms in _FOCUS_TERM_GROUPS.items():
        if any(term in lowered for term in terms):
            return group
    return ""


def _text_matches_focus(text: str, focus_group: str) -> bool:
    if not focus_group:
        return True
    lowered = _normalize_text(text)
    terms = _FOCUS_TERM_GROUPS.get(focus_group, ())
    if not any(term in lowered for term in terms):
        return False
    unrelated = _UNRELATED_TERM_GROUPS.get(focus_group, ())
    if any(term in lowered for term in unrelated) and not any(term in lowered for term in terms):
        return False
    return True


def _looks_like_meta_search_text(text: str) -> bool:
    lowered = _normalize_text(text)
    return any(phrase in lowered for phrase in _META_SEARCH_PHRASES)


def _looks_like_embedded_payload_text(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped:
        return False
    if stripped.startswith("{") and stripped.endswith("}"):
        return True
    payload_markers = (
        '"common_causes"',
        '"solutions"',
        '"links"',
        '"topics_found"',
        '"recommendation"',
        '"summary"',
    )
    return sum(marker in stripped for marker in payload_markers) >= 2


def _filter_links_for_focus(links: list[dict], focus_group: str) -> list[dict]:
    if not focus_group:
        return links
    filtered = []
    for item in links:
        blob = " ".join(
            str(item.get(key) or "")
            for key in ("title", "url", "description", "type")
        )
        if _text_matches_focus(blob, focus_group):
            filtered.append(item)
    return filtered


def _filter_cases_for_focus(cases: list[dict], focus_group: str) -> list[dict]:
    if not focus_group:
        return cases
    filtered = []
    for item in cases:
        blob = " ".join(
            str(item.get(key) or "")
            for key in ("title", "cause", "solution")
        )
        if _text_matches_focus(blob, focus_group):
            filtered.append(item)
    return filtered


def _filter_topics_for_focus(topics: list[dict], focus_group: str) -> list[dict]:
    if not focus_group:
        return topics
    filtered = []
    for item in topics:
        blob = " ".join(
            str(item.get(key) or "")
            for key in ("title", "forum", "url", "key_info")
        )
        if _text_matches_focus(blob, focus_group):
            filtered.append(item)
    return filtered


def _pick_user_ready_summary(data: dict, normalized_cases: list[dict], *, focus_group: str) -> str:
    candidates = [
        str(data.get("parser_summary") or "").strip(),
        str(data.get("summary") or "").strip(),
        str(data.get("recommendation") or "").strip(),
    ]

    for candidate in candidates:
        if not candidate:
            continue
        if _looks_like_embedded_payload_text(candidate):
            continue
        if candidate.lower() in {
            "analysis based on forum topics found",
            "анализ на основе найденных тем форумов",
        }:
            continue
        if _looks_like_meta_search_text(candidate):
            continue
        if focus_group and not _text_matches_focus(candidate, focus_group):
            continue
        return candidate

    for item in normalized_cases:
        cause = str(item.get("cause") or "").strip()
        solution = str(item.get("solution") or "").strip()
        if cause and (not focus_group or _text_matches_focus(cause, focus_group)):
            return cause
        if solution and (not focus_group or _text_matches_focus(solution, focus_group)):
            return solution
    return ""


def _normalize_extracted_cases(raw_cases) -> list[dict]:
    if not isinstance(raw_cases, list):
        return []
    normalized = []
    for item in raw_cases:
        if isinstance(item, dict):
            normalized.append(
                {
                    "title": str(item.get("title") or item.get("symptom_title") or ""),
                    "cause": str(item.get("cause") or item.get("confirmed_cause") or ""),
                    "solution": str(item.get("solution") or item.get("recommended_action") or ""),
                }
            )
    return normalized


def _build_extracted_cases_from_structured(data: dict) -> list[dict]:
    causes = data.get("common_causes") if isinstance(data, dict) else []
    solutions = data.get("solutions") if isinstance(data, dict) else []
    if not isinstance(causes, list) and not isinstance(solutions, list):
        return []

    normalized_causes = []
    for item in causes or []:
        if isinstance(item, dict):
            normalized_causes.append(str(item.get("cause") or "").strip())
        else:
            normalized_causes.append(str(item or "").strip())

    normalized_solutions = []
    for item in solutions or []:
        if isinstance(item, dict):
            title = str(item.get("title") or "").strip()
            description = str(item.get("description") or "").strip()
            normalized_solutions.append("\n".join(part for part in (title, description) if part).strip())
        else:
            normalized_solutions.append(str(item or "").strip())

    max_len = max(len(normalized_causes), len(normalized_solutions), 0)
    extracted_cases = []
    for index in range(max_len):
        extracted_cases.append(
            {
                "title": f"case_{index + 1}",
                "cause": normalized_causes[index] if index < len(normalized_causes) else "",
                "solution": normalized_solutions[index] if index < len(normalized_solutions) else "",
            }
        )
    return extracted_cases


def _build_links_from_topics(topics) -> list[dict]:
    if not isinstance(topics, list):
        return []
    links: list[dict] = []
    for item in topics:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        forum = str(item.get("forum") or "").strip()
        key_info = str(item.get("key_info") or "").strip()
        if not url and not title:
            continue
        link_type = "video" if any(domain in url.lower() for domain in ("youtube.com", "youtu.be", "rutube.ru", "vimeo.com")) else "link"
        links.append(
            {
                "title": title or forum or url,
                "url": url,
                "description": key_info,
                "type": link_type,
            }
        )
    return links


def _build_forums_found(topics) -> list[str]:
    if not isinstance(topics, list):
        return []
    forums: list[str] = []
    for item in topics:
        if not isinstance(item, dict):
            continue
        forum = str(item.get("forum") or "").strip()
        if forum and forum not in forums:
            forums.append(forum)
    return forums


def _has_usable_payload(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    if data.get("error"):
        return False
    if bool(data.get("need_more_info")):
        return True
    for key in ("parser_summary", "summary", "recommendation"):
        if str(data.get(key) or "").strip():
            return True
    if data.get("links") or data.get("topics_found") or data.get("extracted_cases"):
        return True
    return False


def _merge_embedded_json_payload(data: dict) -> dict:
    if not isinstance(data, dict):
        return data

    for key in ("parser_summary", "summary", "recommendation"):
        text = str(data.get(key) or "").strip()
        if "{" not in text or "}" not in text:
            continue
        parsed = extract_json(text)
        if not isinstance(parsed, dict):
            continue
        if not any(parsed.get(field) for field in ("summary", "recommendation", "common_causes", "solutions", "links", "topics_found")):
            continue

        merged = dict(data)
        for field in (
            "summary",
            "recommendation",
            "common_causes",
            "solutions",
            "unlikely_causes",
            "regional_insights",
            "links",
            "topics_found",
            "total_topics",
            "confidence",
            "need_more_info",
            "clarifying_question",
        ):
            if parsed.get(field):
                merged[field] = parsed[field]
        merged["_embedded_json_extracted"] = True
        return merged

    return data


async def parse_diagnostic(router_json: dict) -> dict:
    deep_search = bool(router_json.get("deep_search", False))
    query = str(
        router_json.get("query")
        or router_json.get("symptom")
        or router_json.get("text")
        or ""
    ).strip()

    payload = DiagnosticRequest(
        query=query,
        lang=str(router_json.get("language", "en") or "en"),
        car_info=str(router_json.get("active_car") or router_json.get("car_info") or ""),
        conversation_history=str(router_json.get("conversation_history") or ""),
        mode="deep" if deep_search else "normal",
    )
    focus_group = _extract_focus_group_safe(query)

    data = _merge_embedded_json_payload(await diagnose(payload))
    if not _has_usable_payload(data):
        raise ParserUnavailableError(
            str(data.get("error") or data.get("summary") or "Parser returned no usable data.")
        )

    topics_found = data.get("topics_found", [])
    forums_found = data.get("forums_found")
    links = data.get("links", [])
    extracted_cases = data.get("extracted_cases", [])
    normalized_cases = _normalize_extracted_cases(extracted_cases)
    if not normalized_cases:
        normalized_cases = _build_extracted_cases_from_structured(data)

    parser_summary = str(data.get("parser_summary") or data.get("summary") or "").strip()
    if parser_summary.lower() in {
        "analysis based on forum topics found",
        "анализ на основе найденных тем форумов",
    }:
        parser_summary = ""
    if not parser_summary:
        parser_summary = str(data.get("recommendation") or "").strip()
    if not parser_summary and normalized_cases:
        parser_summary = str(normalized_cases[0].get("cause") or normalized_cases[0].get("solution") or "").strip()

    normalized_links = _normalize_links(links)
    if not normalized_links:
        normalized_links = _build_links_from_topics(topics_found)

    filtered_topics = topics_found if isinstance(topics_found, list) else []
    filtered_topics = _filter_topics_for_focus(filtered_topics, focus_group)
    normalized_cases = _filter_cases_for_focus(normalized_cases, focus_group)
    normalized_links = _filter_links_for_focus(normalized_links, focus_group)

    parser_summary = _pick_user_ready_summary(
        data,
        normalized_cases,
        focus_group=focus_group,
    )

    normalized_forums = forums_found if isinstance(forums_found, list) else _build_forums_found(topics_found)
    if focus_group and filtered_topics:
        normalized_forums = _build_forums_found(filtered_topics)

    return {
        "forums_found": normalized_forums,
        "links": normalized_links,
        "extracted_cases": normalized_cases,
        "parser_summary": parser_summary,
        "topics_found": filtered_topics,
        "_raw": data,
    }
