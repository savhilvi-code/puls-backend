import json
import os
import re
from functools import lru_cache

from openai import OpenAI

from app.schemas.router import RouterDecision
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
        raise OpenAIRouterUnavailableError(f"Failed to initialize OpenAI client: {exc}") from exc


def _extract_json(text: str) -> dict:
    candidate = (text or "").strip()
    match = re.search(r"\{[\s\S]*\}", candidate)
    if match:
        candidate = match.group(0)
    data = json.loads(candidate)
    if not isinstance(data, dict):
        raise ValueError("Router response is not a JSON object.")
    return data


def _build_user_context(text: str, language: str, car_info: str, conversation_history: str) -> str:
    return (
        f"User language hint: {language}\n"
        f"User text: {text}\n"
        f"Car info from profile: {car_info or ''}\n"
        f"Conversation history: {conversation_history or ''}\n\n"
        "Return only JSON."
    )


ROUTER_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "message_type": {"type": "string", "enum": ["general", "new_diagnostic", "followup_deep", "helped_feedback", "clarification"]},
        "language": {"type": "string"},
        "need_car_info": {"type": "boolean"},
        "ready_to_search": {"type": "boolean"},
        "deep_search": {"type": "boolean"},
        "active_car": {"type": "string"},
        "symptom": {"type": "string"},
        "response": {"type": "string"},
    },
    "required": [
        "message_type",
        "language",
        "need_car_info",
        "ready_to_search",
        "deep_search",
        "active_car",
        "symptom",
        "response",
    ],
    "additionalProperties": False,
}


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


async def generate_router_decision(
    *, prompt: str, text: str, language: str, car_info: str, conversation_history: str
) -> RouterDecision:
    if not is_configured():
        raise OpenAIRouterUnavailableError("OpenAI is not configured. Set OPENAI_API_KEY.")

    try:
        client = get_openai_client()
        response = client.responses.create(
            model="gpt-4o-mini",
            instructions=prompt,
            input=_build_user_context(
                text=text,
                language=language,
                car_info=car_info,
                conversation_history=conversation_history,
            ),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "router_decision",
                    "description": "PULS dialog router output.",
                    "schema": ROUTER_JSON_SCHEMA,
                    "strict": True,
                }
            },
        )
        raw_text = getattr(response, "output_text", "") or ""
        data = _extract_json(raw_text)
        return RouterDecision(
            message_type=str(data.get("message_type") or "general"),
            language=str(data.get("language") or language or "en"),
            need_car_info=bool(data.get("need_car_info", False)),
            ready_to_search=bool(data.get("ready_to_search", False)),
            deep_search=bool(data.get("deep_search", False)),
            active_car=str(data.get("active_car") or ""),
            symptom=str(data.get("symptom") or ""),
            response=str(data.get("response") or ""),
        )
    except OpenAIRouterUnavailableError:
        raise
    except Exception as exc:
        raise OpenAIRouterUnavailableError(f"OpenAI router failed: {exc}") from exc


async def classify_message(*, prompt: str, text: str, language: str, car_info: str, conversation_history: str):
    return await generate_router_decision(
        prompt=prompt,
        text=text,
        language=language,
        car_info=car_info,
        conversation_history=conversation_history,
    )


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
                "Preserve meaning, line breaks, bullet structure, URLs, car brands, model codes, engine codes, "
                "and technical abbreviations such as MAF, AFM, VAF, ECU, OBD. "
                "Do not add explanations or commentary. Return only JSON."
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


async def generate_diagnostic_answer(*, text: str, car_info: str, language: str):
    return None
