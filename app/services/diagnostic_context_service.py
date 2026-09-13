from __future__ import annotations

from typing import Any


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _vehicle_context(resolved_vehicle: dict | None) -> dict:
    vehicle = resolved_vehicle or {}
    return {
        "id": vehicle.get("id"),
        "brand": vehicle.get("brand") or "",
        "model": vehicle.get("model") or "",
        "year": vehicle.get("year") or "",
        "engine": vehicle.get("engine") or "",
    }


def _case_context(match: dict | None, *, match_kind: str) -> dict | None:
    if not isinstance(match, dict):
        return None

    row = match.get("row") if isinstance(match.get("row"), dict) else {}
    source_type = (
        _clean_text(match.get("source_type"))
        or _clean_text(match.get("source_table"))
        or _clean_text(row.get("source_table"))
        or _clean_text(row.get("source_type"))
        or match_kind
    )
    links = match.get("links")
    if not isinstance(links, list):
        links = row.get("forum_links") if isinstance(row.get("forum_links"), list) else []

    return {
        "available": True,
        "kind": match_kind,
        "source_type": source_type,
        "case_id": match.get("id") or row.get("id"),
        "answer": _clean_text(match.get("answer") or row.get("full_answer") or row.get("recommended_action")),
        "links": links,
        "row": row,
    }


def build_diagnostic_context(
    *,
    state,
    normalized,
    user,
    resolved_vehicle: dict | None,
    latest_context: dict | None,
    effective_symptom: str,
    parser_query: str = "",
    parser_history: str = "",
    parsed_case: dict | None = None,
    diagnosis_text: str = "",
    probable_causes: list[str] | None = None,
    first_checks: list[str] | None = None,
    less_likely: list[str] | None = None,
    response_links: list[dict] | None = None,
    internal_match: dict | None = None,
    internal_match_kind: str = "kb",
) -> dict:
    """Build the vendor-neutral context passed to diagnostic synthesis."""

    probable_causes = probable_causes or []
    first_checks = first_checks or []
    less_likely = less_likely or []
    response_links = response_links or []
    parsed_case = parsed_case or {}
    latest_context = latest_context or {}
    internal_context = _case_context(internal_match, match_kind=internal_match_kind)
    internal_answer = _clean_text((internal_context or {}).get("answer"))

    return {
        "canonical_output_language": "en",
        "user_language": getattr(state, "language", "") or getattr(normalized, "language", ""),
        "active_vehicle": (
            getattr(state, "active_car", "")
            or getattr(normalized, "car_info", "")
            or getattr(user, "car_info", "")
        ),
        "vehicle": _vehicle_context(resolved_vehicle),
        "current_symptom": _clean_text(effective_symptom),
        "parser_query": _clean_text(parser_query),
        "conversation_history": _clean_text(parser_history or getattr(user, "conversation_history", "")),
        "latest_conversation_context": latest_context,
        "service_logs": {"available_in_current_flow": False, "items": []},
        "dtc": {"available_in_current_flow": False, "items": []},
        "internal_knowledge": internal_context or {"available": False},
        "kb_match": internal_context if internal_match_kind == "kb" else None,
        "history_match": internal_context if internal_match_kind == "history" else None,
        "parser_result": parsed_case or None,
        "deep_search_result": parsed_case if getattr(state, "should_deep_search", False) else None,
        "aggregated_evidence": {
            "internal_summary": internal_answer,
            "parser_summary": _clean_text(diagnosis_text),
            "probable_causes": probable_causes,
            "first_checks": first_checks,
            "less_likely": less_likely,
            "source_links": response_links,
            "confidence": _clean_text((parsed_case.get("_raw") or {}).get("confidence") if parsed_case else ""),
        },
    }
