import json
import os
import re
from functools import lru_cache

from openai import OpenAI

from app.schemas.router import RouterDecision


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


async def generate_diagnostic_answer(*, text: str, car_info: str, language: str):
    return None
