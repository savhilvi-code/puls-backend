import os
from typing import Any

import httpx


class ParserUnavailableError(RuntimeError):
    pass


def _parser_url() -> str:
    return str(os.getenv("PARSER_API_URL", "") or "").strip()


def _normalize_links(raw_links: Any) -> list[dict]:
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


def _normalize_extracted_cases(raw_cases: Any) -> list[dict]:
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


async def parse_diagnostic(router_json: dict) -> dict:
    url = _parser_url()
    if not url:
        raise ParserUnavailableError("Parser is not configured. Set PARSER_API_URL.")

    payload = {
        "active_car": router_json.get("active_car", ""),
        "symptom": router_json.get("symptom", ""),
        "deep_search": bool(router_json.get("deep_search", False)),
        "language": router_json.get("language", "en"),
    }

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        raise ParserUnavailableError(f"Parser failed with HTTP {exc.response.status_code}.") from exc
    except httpx.RequestError as exc:
        raise ParserUnavailableError(f"Parser request failed: {exc}") from exc
    except ValueError as exc:
        raise ParserUnavailableError(f"Parser returned invalid JSON: {exc}") from exc

    forums_found = data.get("forums_found", [])
    links = _normalize_links(data.get("links", []))
    extracted_cases = _normalize_extracted_cases(data.get("extracted_cases", []))
    parser_summary = str(data.get("parser_summary") or data.get("summary") or "")

    if not parser_summary and extracted_cases:
        parser_summary = extracted_cases[0].get("solution") or extracted_cases[0].get("cause") or ""

    return {
        "forums_found": forums_found if isinstance(forums_found, list) else [],
        "links": links,
        "extracted_cases": extracted_cases,
        "parser_summary": parser_summary,
    }
