from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache

from openai import OpenAI

from app.utils.language import detect_language, normalize_language_code


class OpenAIRouterUnavailableError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


@lru_cache(maxsize=1)
def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise OpenAIRouterUnavailableError("OpenAI is not configured. Set OPENAI_API_KEY.")
    try:
        return OpenAI(api_key=api_key)
    except Exception as exc:  # pragma: no cover
        raise OpenAIRouterUnavailableError("Failed to initialize OpenAI client.") from exc


def _extract_json(text: str) -> dict:
    candidate = (text or "").strip()
    match = re.search(r"\{[\s\S]*\}", candidate)
    if match:
        candidate = match.group(0)
    data = json.loads(candidate)
    if not isinstance(data, dict):
        raise ValueError("OpenAI response is not a JSON object.")
    return data


TRANSLATION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {"type": "string"},
        }
    },
    "required": ["translations"],
    "additionalProperties": False,
}


CHAT_REPLY_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
    },
    "required": ["reply"],
    "additionalProperties": False,
}


TURN_INTENT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["GENERAL", "META", "DIAGNOSTIC", "REFERENCE", "HOWTO"],
        },
        "external_search": {"type": "boolean"},
        "source_preference": {
            "type": "string",
            "enum": ["ANY", "FORUM", "MANUAL", "WEB"],
        },
        "visual_requested": {"type": "boolean"},
        "link_requested": {"type": "boolean"},
        "resolved_query": {"type": "string"},
    },
    "required": [
        "intent", "external_search", "source_preference", "visual_requested",
        "link_requested", "resolved_query",
    ],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class TurnIntent:
    intent: str = "GENERAL"
    external_search: bool = False
    source_preference: str = "ANY"
    visual_requested: bool = False
    link_requested: bool = False
    resolved_query: str = ""


async def classify_turn_intent(
    *,
    user_text: str,
    language: str,
    recent_conversation: list[dict] | None = None,
    active_vehicle: str = "",
    active_problem: str = "",
) -> TurnIntent | None:
    """Classify routing semantically in one language-neutral structured call.

    The compact prior-turn window exists specifically for elliptical follow-ups
    such as "on a forum" or "give me the link".  Search still receives only the
    resolved subject, never the full transcript.
    """
    if not is_configured():
        return None

    compact_history = []
    for item in (recent_conversation or [])[-6:]:
        compact_history.append({
            "role": str(item.get("role") or "")[:20],
            "text": str(item.get("text") or item.get("content") or "")[:500],
        })
    payload = {
        "language": normalize_language_code(language),
        "user_text": str(user_text or "")[:1200],
        "recent_conversation": compact_history,
        "active_vehicle": str(active_vehicle or "")[:240],
        "active_problem": str(active_problem or "")[:500],
    }
    try:
        response = get_openai_client().responses.create(
            model="gpt-4o-mini",
            instructions=(
                "Classify the current PULS turn by meaning, independently of language. "
                "REFERENCE means verified technical facts, manuals, specifications, component identification, "
                "external sources or real visual references. HOWTO means a requested procedure. DIAGNOSTIC means "
                "investigating a vehicle fault. external_search is true only when the user explicitly asks PULS "
                "to search/find/check an external forum, manual, web source, link, real image/diagram, or when a "
                "short follow-up continues such an unresolved request. Resolve elliptical follow-ups from the "
                "compact history. resolved_query must be a concise standalone query preserving vehicle, component "
                "or procedure, source preference, visual intent and requested link; do not invent facts. "
                "Return only JSON."
            ),
            input=json.dumps(payload, ensure_ascii=False),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "puls_turn_intent",
                    "description": "Semantic routing decision for one PULS turn.",
                    "schema": TURN_INTENT_JSON_SCHEMA,
                    "strict": True,
                }
            },
        )
        data = _extract_json(getattr(response, "output_text", "") or "")
        return TurnIntent(
            intent=str(data.get("intent") or "GENERAL").upper(),
            external_search=bool(data.get("external_search")),
            source_preference=str(data.get("source_preference") or "ANY").upper(),
            visual_requested=bool(data.get("visual_requested")),
            link_requested=bool(data.get("link_requested")),
            resolved_query=str(data.get("resolved_query") or "").strip()[:1600],
        )
    except Exception:
        return None


async def translate_segments(*, segments: list[str], target_language: str) -> list[str]:
    normalized_target = normalize_language_code(target_language)
    prepared = [str(segment or "") for segment in segments]
    if not prepared:
        return []

    translatable_indexes = [
        index
        for index, segment in enumerate(prepared)
        if segment.strip() and detect_language(segment) != normalized_target
    ]
    if not translatable_indexes or not is_configured():
        return prepared

    payload = {
        "target_language": normalized_target,
        "segments": [prepared[index] for index in translatable_indexes],
    }
    try:
        client = get_openai_client()
        response = client.responses.create(
            model="gpt-4o-mini",
            instructions=(
                "Translate each input segment into the requested target language. "
                "Preserve URLs, vehicle brands, model codes, engine codes, and technical abbreviations. "
                "Do not add explanations. Return only JSON."
            ),
            input=json.dumps(payload, ensure_ascii=False),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "segment_translations",
                    "description": "Translated text segments.",
                    "schema": TRANSLATION_JSON_SCHEMA,
                    "strict": True,
                }
            },
        )
        data = _extract_json(getattr(response, "output_text", "") or "")
        translations = data.get("translations")
        if not isinstance(translations, list) or len(translations) != len(translatable_indexes):
            return prepared
        localized = list(prepared)
        for index, translated in zip(translatable_indexes, translations):
            localized[index] = str(translated or localized[index])
        return localized
    except Exception:
        return prepared


async def generate_natural_chat_reply(
    *,
    mode: str,
    user_text: str,
    language: str,
    recent_conversation: list[dict] | None = None,
    active_vehicle: str = "",
    automotive_context: str = "",
    pending_clarification: str = "",
    stored_facts: list[str] | None = None,
    context_relevant: bool = False,
) -> str:
    if not is_configured():
        raise OpenAIRouterUnavailableError("OpenAI is not configured. Set OPENAI_API_KEY.")

    payload = {
        "mode": mode,
        "language": normalize_language_code(language),
        "user_text": user_text,
        "recent_conversation": recent_conversation or [],
        "active_vehicle": active_vehicle,
        "automotive_context": automotive_context,
        "pending_clarification": pending_clarification,
        "stored_facts": stored_facts or [],
        "context_relevant_to_current_message": bool(context_relevant),
    }
    client = get_openai_client()
    response = client.responses.create(
        model="gpt-4o-mini",
        instructions=(
            "You are PULS, a natural conversational assistant specialized around cars. "
            "Answer the current user turn directly in the user's language. "
            "Use only the supplied context. Persisted vehicle/problem context is silent background: mention it only "
            "when the user is continuing that topic or explicitly asks about memory/history/context. "
            "For greetings, casual small talk, and meta-chat, do not diagnose, do not ask intake questions, "
            "and do not mention parser, search, quota, database state, sources, or internal routing. "
            "For clarification, ask one useful question only. "
            "Return clean plain text only: no Markdown headings or tables."
        ),
        input=json.dumps(payload, ensure_ascii=False),
        text={
            "format": {
                "type": "json_schema",
                "name": "natural_chat_reply",
                "description": "Plain-text natural PULS chat reply.",
                "schema": CHAT_REPLY_JSON_SCHEMA,
                "strict": True,
            }
        },
    )
    data = _extract_json(getattr(response, "output_text", "") or "")
    return str(data.get("reply") or "").strip()
