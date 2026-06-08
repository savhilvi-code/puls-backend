from __future__ import annotations

from app.schemas.parser import DiagnosticRequest
from app.services.parser_engine import diagnose


class ParserUnavailableError(RuntimeError):
    pass


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
        raise ParserUnavailableError(str(data.get("error") or "Parser unavailable"))

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
