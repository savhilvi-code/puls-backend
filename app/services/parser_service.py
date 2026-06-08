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

    forums_found = data.get("forums_found")
    topics_found = data.get("topics_found", [])
    links = data.get("links", [])
    extracted_cases = data.get("extracted_cases", [])
    parser_summary = str(data.get("parser_summary") or data.get("summary") or data.get("recommendation") or "")

    return {
        "forums_found": forums_found if isinstance(forums_found, list) else [],
        "links": links if isinstance(links, list) else [],
        "extracted_cases": extracted_cases if isinstance(extracted_cases, list) else [],
        "parser_summary": parser_summary,
        "topics_found": topics_found if isinstance(topics_found, list) else [],
        "_raw": data,
    }
