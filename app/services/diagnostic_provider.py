from __future__ import annotations

import json
import os
import re
from typing import Any

try:  # pragma: no cover - optional dependency in some local environments
    from openai import OpenAI  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    OpenAI = None

from app.services.provider_config import get_diagnostic_provider, get_openai_diagnostic_model


DIAGNOSTIC_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "most_likely": {"type": "string"},
        "why": {"type": "string"},
        "first_checks": {
            "type": "array",
            "items": {"type": "string"},
        },
        "less_likely": {
            "type": "array",
            "items": {"type": "string"},
        },
        "what_would_change_diagnosis": {
            "type": "array",
            "items": {"type": "string"},
        },
        "short_conclusion": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "description": {"type": "string"},
                    "type": {"type": "string"},
                },
                "required": ["title", "url", "description", "type"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "most_likely",
        "why",
        "first_checks",
        "less_likely",
        "what_would_change_diagnosis",
        "short_conclusion",
        "confidence",
        "sources",
    ],
    "additionalProperties": False,
}


SYSTEM_PROMPT = """You are the PULS final diagnostic synthesis provider.

Use only the structured PULS context supplied in the request.
Do not browse the web. Do not call search. Do not invent sources or facts.

Return canonical English JSON only. The user-facing localization happens later.
Separate known facts, evidence-supported inference, and uncertainty.
If the evidence is insufficient, say so explicitly and keep confidence low.
"""


def _extract_json(text: str) -> dict:
    candidate = str(text or "").strip()
    match = re.search(r"\{[\s\S]*\}", candidate)
    if match:
        candidate = match.group(0)
    parsed = json.loads(candidate)
    if not isinstance(parsed, dict):
        raise ValueError("Diagnostic provider returned non-object JSON.")
    return parsed


def _clean_string(value: Any) -> str:
    return str(value or "").strip()


def _clean_string_list(value: Any, *, limit: int = 6) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        text = _clean_string(item)
        if text:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _clean_sources(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    sources: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        url = _clean_string(item.get("url"))
        title = _clean_string(item.get("title") or item.get("forum") or url)
        if not url and not title:
            continue
        sources.append(
            {
                "title": title,
                "url": url,
                "description": _clean_string(item.get("description") or item.get("key_info")),
                "type": _clean_string(item.get("type") or "link"),
            }
        )
    return sources[:10]


def normalize_diagnostic_result(value: Any) -> dict | None:
    if not isinstance(value, dict):
        return None

    result = {
        "most_likely": _clean_string(value.get("most_likely")),
        "why": _clean_string(value.get("why")),
        "first_checks": _clean_string_list(value.get("first_checks")),
        "less_likely": _clean_string_list(value.get("less_likely")),
        "what_would_change_diagnosis": _clean_string_list(value.get("what_would_change_diagnosis")),
        "short_conclusion": _clean_string(value.get("short_conclusion")),
        "confidence": _clean_string(value.get("confidence")).lower(),
        "sources": _clean_sources(value.get("sources")),
    }
    if result["confidence"] not in {"high", "medium", "low"}:
        result["confidence"] = "low"
    if not (result["most_likely"] or result["short_conclusion"] or result["first_checks"]):
        return None
    return result


def _run_openai_diagnostic_provider(context: dict[str, Any]) -> dict | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = get_openai_diagnostic_model()
    if not api_key or not model or OpenAI is None:
        return None

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=json.dumps(context, ensure_ascii=False),
        text={
            "format": {
                "type": "json_schema",
                "name": "puls_diagnostic_synthesis",
                "description": "Canonical English final diagnostic synthesis for PULS.",
                "schema": DIAGNOSTIC_RESULT_SCHEMA,
                "strict": True,
            }
        },
    )
    data = _extract_json(getattr(response, "output_text", "") or "")
    return normalize_diagnostic_result(data)


def run_diagnostic_provider(context: dict[str, Any]) -> dict | None:
    provider = get_diagnostic_provider()
    if provider == "none":
        return None
    if provider == "openai":
        try:
            return _run_openai_diagnostic_provider(context)
        except Exception:
            return None
    return None
