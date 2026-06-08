from __future__ import annotations

from urllib.parse import urlparse, urlunparse

import httpx

from app.schemas.parser import DiagnosticRequest
from app.services.parser_engine import diagnose


class ParserUnavailableError(RuntimeError):
    pass


DEFAULT_PARSER_API_URL = "https://car-diagnostic-api.onrender.com/search"


def _resolve_parser_endpoint(url: str) -> str:
    parsed = urlparse(url)
    path = (parsed.path or "").rstrip("/")
    if path.endswith("/search") or path.endswith("/diagnose"):
        return url
    if not path:
        path = "/search"
    else:
        path = f"{path}/search"
    return urlunparse(parsed._replace(path=path))


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


async def _fallback_remote_parse(payload: DiagnosticRequest, deep_search: bool) -> dict:
    url = DEFAULT_PARSER_API_URL
    endpoint = _resolve_parser_endpoint(url)
    body = {
        "query": payload.query,
        "lang": payload.lang,
        "car_info": payload.car_info or "",
        "conversation_history": payload.conversation_history or "",
        "mode": "deep" if deep_search else "normal",
    }

    try:
        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
            response = await client.post(endpoint, json=body)
            if response.status_code in {404, 405} and not endpoint.rstrip("/").endswith("/search"):
                alternate = endpoint.rstrip("/")
                if alternate.endswith("/diagnose"):
                    alternate = alternate[: -len("/diagnose")] + "/search"
                else:
                    alternate = alternate + "/search"
                response = await client.post(alternate, json=body)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        raise ParserUnavailableError(f"Parser request failed: {exc}") from exc

    forums_found = data.get("forums_found")
    topics_found = data.get("topics_found", [])
    links = _normalize_links(data.get("links", []))
    if not links:
        links = _build_links_from_topics(topics_found)
    extracted_cases = _normalize_extracted_cases(data.get("extracted_cases", []))
    if not extracted_cases:
        solutions = data.get("solutions", [])
        common_causes = data.get("common_causes", [])
        if isinstance(solutions, list):
            for item in solutions:
                if not isinstance(item, dict):
                    continue
                extracted_cases.append(
                    {
                        "title": str(item.get("title") or ""),
                        "cause": str(item.get("description") or ""),
                        "solution": str(item.get("description") or item.get("title") or ""),
                    }
                )
        if not extracted_cases and isinstance(common_causes, list):
            for item in common_causes:
                if not isinstance(item, dict):
                    continue
                extracted_cases.append(
                    {
                        "title": str(item.get("cause") or ""),
                        "cause": str(item.get("cause") or ""),
                        "solution": str(item.get("cause") or ""),
                    }
                )
    parser_summary = str(data.get("parser_summary") or data.get("summary") or data.get("recommendation") or "")
    if not parser_summary and extracted_cases:
        parser_summary = extracted_cases[0].get("solution") or extracted_cases[0].get("cause") or ""

    return {
        "forums_found": forums_found if isinstance(forums_found, list) else _build_forums_found(topics_found),
        "links": links,
        "extracted_cases": extracted_cases,
        "parser_summary": parser_summary,
        "topics_found": topics_found if isinstance(topics_found, list) else [],
        "_raw": data,
    }


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
    if "error" in data and not data.get("summary"):
        return await _fallback_remote_parse(payload, deep_search)

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
