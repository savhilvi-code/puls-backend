from pathlib import Path

from app.schemas.router import RouterDecision
from app.services.openai_service import OpenAIRouterUnavailableError, classify_message
from app.utils.language import normalize_language_code

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "router_prompt.txt"


def _normalize(text: str) -> str:
    return " ".join(str(text or "").strip().lower().strip(" \t\n\r,.:;!?").split())


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = _normalize(text)
    return any(term in lowered for term in terms)


def _has_car_reference(text: str) -> bool:
    return _contains_any(
        text,
        (
            "toyota",
            "nissan",
            "honda",
            "mazda",
            "bmw",
            "audi",
            "volkswagen",
            "vw",
            "lexus",
            "x-trail",
            "xtrail",
            "corolla",
        ),
    )


def _has_automotive_content(text: str) -> bool:
    return _contains_any(
        text,
        (
            "engine",
            "rpm",
            "idle",
            "dtc",
            "obd",
            "vibrat",
            "stall",
            "misfire",
            "acceleration",
            "under load",
            "oil",
            "fluid",
            "repair",
            "replace",
            "\u043c\u0430\u0448\u0438\u043d",
            "\u0434\u0432\u0438\u0433\u0430\u0442",
            "\u0432\u0438\u0431\u0440\u0430\u0446",
            "\u0442\u0440\u043e\u0438\u0442",
            "\u043d\u0435 \u0442\u044f\u043d\u0435\u0442",
            "\u0440\u0430\u0437\u0433\u043e\u043d",
            "\u0445\u043e\u043b\u043e\u0434",
            "\u0433\u043e\u0440\u044f\u0447",
            "\u043f\u0440\u043e\u0433\u0440\u0435\u0432",
            "\u0437\u0430\u043c\u0435\u043d",
            "\u043e\u0448\u0438\u0431",
            "\u043c\u0430\u0441\u043b\u043e",
        ),
    )


def _is_social_general_text(text: str) -> bool:
    lowered = _normalize(text)
    if not lowered or _has_car_reference(lowered) or _has_automotive_content(lowered):
        return False
    return _contains_any(
        lowered,
        (
            "hi",
            "hello",
            "hey",
            "how are you",
            "thanks",
            "thank you",
            "ok",
            "okay",
            "\u043f\u0440\u0438\u0432\u0435\u0442",
            "\u0434\u043e\u0431\u0440\u044b\u0439 \u0434\u0435\u043d\u044c",
            "\u043a\u0430\u043a \u0434\u0435\u043b\u0430",
            "\u043a\u0430\u043a \u0442\u044b",
            "\u043a\u0430\u043a \u0436\u0438\u0437\u043d\u044c",
            "\u0441\u043f\u0430\u0441\u0438\u0431\u043e",
            "\u043f\u043e\u043d\u044f\u0442\u043d\u043e",
        ),
    )


def _is_negative_feedback(text: str) -> bool:
    return _contains_any(text, ("not helped", "did not help", "still", "\u043d\u0435 \u043f\u043e\u043c\u043e\u0433\u043b\u043e", "\u0438\u0449\u0438 \u0433\u043b\u0443\u0431\u0436\u0435"))


def _is_positive_feedback(text: str) -> bool:
    return _normalize(text) in {"helped", "fixed", "solved", "\u043f\u043e\u043c\u043e\u0433\u043b\u043e", "\u0440\u0435\u0448\u0435\u043d\u043e"}


def _local_router(text: str, language: str) -> RouterDecision:
    language = normalize_language_code(language)
    if _is_social_general_text(text):
        return RouterDecision(message_type="general", language=language)
    if _is_negative_feedback(text):
        return RouterDecision(
            message_type="followup_deep",
            language=language,
            ready_to_search=True,
            deep_search=True,
            user_says_not_helped=True,
            symptom=str(text or "")[:120],
        )
    if _is_positive_feedback(text):
        return RouterDecision(message_type="helped_feedback", language=language, user_says_helped=True)
    return RouterDecision(
        message_type="new_diagnostic",
        language=language,
        ready_to_search=bool(str(text or "").strip()),
        symptom=str(text or "")[:120],
    )


def _stabilize_decision(text: str, user, decision: RouterDecision) -> RouterDecision:
    if _is_social_general_text(text):
        return decision.model_copy(
            update={
                "message_type": "general",
                "need_car_info": False,
                "need_clarification": False,
                "ready_to_search": False,
                "deep_search": False,
                "user_says_helped": False,
                "user_says_not_helped": False,
                "response": "",
            }
        )
    if _is_negative_feedback(text):
        return decision.model_copy(
            update={
                "message_type": "followup_deep",
                "need_car_info": False,
                "ready_to_search": True,
                "deep_search": True,
                "user_says_not_helped": True,
            }
        )
    if _is_positive_feedback(text):
        return decision.model_copy(
            update={
                "message_type": "helped_feedback",
                "need_car_info": False,
                "ready_to_search": False,
                "deep_search": False,
                "user_says_helped": True,
            }
        )
    if _has_car_reference(text) or _has_automotive_content(text):
        return decision.model_copy(
            update={
                "message_type": "new_diagnostic",
                "need_car_info": False,
                "ready_to_search": True,
                "response": "",
            }
        )
    return decision


async def route_message(normalized, user) -> RouterDecision:
    prompt = PROMPT_PATH.read_text(encoding="utf-8") if PROMPT_PATH.exists() else ""
    try:
        decision = await classify_message(
            prompt=prompt,
            text=normalized.text,
            language=normalized.language,
            car_info=normalized.car_info,
            conversation_history=user.conversation_history,
        )
    except OpenAIRouterUnavailableError:
        decision = _local_router(normalized.text, normalized.language)
    except Exception:
        decision = _local_router(normalized.text, normalized.language)
    return _stabilize_decision(normalized.text, user, decision)
