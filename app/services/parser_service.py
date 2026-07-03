from __future__ import annotations

from app.schemas.parser import DiagnosticRequest
from app.services.parser_engine import diagnose


class ParserUnavailableError(RuntimeError):
    pass


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

    data = await diagnose(payload)
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

    normalized_forums = forums_found if isinstance(forums_found, list) else _build_forums_found(topics_found)

    return {
        "forums_found": normalized_forums,
        "links": normalized_links,
        "extracted_cases": normalized_cases,
        "parser_summary": parser_summary,
        "topics_found": topics_found if isinstance(topics_found, list) else [],
        "_raw": data,
    }
