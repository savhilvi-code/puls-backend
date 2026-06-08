from pathlib import Path

from fastapi import HTTPException

from app.schemas.router import RouterDecision
from app.services.openai_service import OpenAIRouterUnavailableError, classify_message
from app.utils.language import normalize_language_code

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "router_prompt.txt"

_CAR_HINTS = ("nissan", "toyota", "honda", "bmw", "audi", "volkswagen", "vw", "ford", "mazda", "xtrail", "x-trail", "sr20vet", "sr20", "pnt30")
_PROBLEM_HINTS = (
    "плохо",
    "не работает",
    "не заводится",
    "заводится",
    "теряет тягу",
    "потеря тяги",
    "нет тяги",
    "не тянет",
    "тупит",
    "дергается",
    "провал",
    "мощност",
    "разгон",
    "на холодную",
    "на горячую",
    "на прогретую",
    "cold",
    "stall",
    "stalls",
    "loss of power",
    "turbo",
    "engine",
)
_FEEDBACK_HELPED = ("helped", "fixed", "solved", "works", "помогло", "исправлено", "решено", "работает")
_FEEDBACK_DEEP = ("не помогло", "ищи глубже", "нужно больше информации", "more details", "not helped", "still")
_GREETINGS = ("hi", "hello", "hey", "привет", "здравствуй", "здравствуйте", "добрый день", "доброе утро", "добрый вечер")


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    lowered = str(text or "").lower()
    return any(token in lowered for token in tokens)


def _has_car_hint(text: str) -> bool:
    return _contains_any(text, _CAR_HINTS)


def _has_problem_hint(text: str) -> bool:
    return _contains_any(text, _PROBLEM_HINTS)


def _has_feedback_helped(text: str) -> bool:
    return _contains_any(text, _FEEDBACK_HELPED)


def _has_feedback_deep(text: str) -> bool:
    return _contains_any(text, _FEEDBACK_DEEP)


def _has_diagnostic_intent(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(
        token in lowered
        for token in (
            "как заменить",
            "как поменять",
            "как снять",
            "как починить",
            "почему",
            "не работает",
            "не заводится",
            "теряет тягу",
            "нет тяги",
            "тупит",
            "дергается",
            "стучит",
            "свистит",
            "дымит",
            "горит",
            "шум",
            "ошибк",
            "диагност",
            "ремонт",
            "проверить",
            "устранить",
            "заменить",
            "поменять",
            "починить",
            "прикуриватель",
            "engine",
            "turbo",
            "stall",
            "stalls",
            "loss of power",
        )
    ) or "?" in lowered


def _is_greeting(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if lowered in _GREETINGS:
        return True
    for token in _GREETINGS:
        if not lowered.startswith(token + " "):
            continue
        rest = lowered[len(token):].strip(" \t\n\r,.:;!?")
        if not rest:
            return True
        if _has_diagnostic_intent(rest):
            return False
        if len(rest) <= 18:
            return True
    return False


def _local_router(text: str, language: str) -> RouterDecision:
    lowered = text.lower().strip()
    language = normalize_language_code(language)

    negative = {"not helped", "did not help", "still", "deeper", "more details"}
    positive = {"helped", "fixed", "solved", "works", "thanks"}
    greetings = {"hi", "hello", "hey", "привет", "здравствуйте", "здравствуй"}

    if _is_greeting(lowered):
        return RouterDecision(
            message_type="general",
            language=language,
            need_car_info=False,
            need_clarification=False,
            ready_to_search=False,
            deep_search=False,
            user_says_helped=False,
            user_says_not_helped=False,
            question="",
            car_info="",
            active_car="",
            symptom="",
            response="Hi! Describe the car issue and I'll help.",
        )

    if any(token in lowered for token in negative):
        return RouterDecision(
            message_type="followup_deep",
            language=language,
            need_car_info=False,
            need_clarification=False,
            ready_to_search=True,
            deep_search=True,
            user_says_helped=False,
            user_says_not_helped=True,
            question="",
            car_info="",
            active_car="",
            symptom=text[:120],
            response="Let's dig deeper.",
        )

    if any(token in lowered for token in positive):
        return RouterDecision(
            message_type="helped_feedback",
            language=language,
            need_car_info=False,
            need_clarification=False,
            ready_to_search=False,
            deep_search=False,
            user_says_helped=True,
            user_says_not_helped=False,
            question="",
            car_info="",
            active_car="",
            symptom="",
            response="Glad it helped.",
        )

    need_car_info = not bool(text)
    return RouterDecision(
        message_type="new_diagnostic",
        language=language,
        need_car_info=need_car_info,
        need_clarification=False,
        ready_to_search=True,
        deep_search=False,
        user_says_helped=False,
        user_says_not_helped=False,
        question="",
        car_info="",
        active_car="",
        symptom=text[:120],
        response="",
    )


async def route_message(normalized, user) -> RouterDecision:
    prompt = ""
    if PROMPT_PATH.exists():
        prompt = PROMPT_PATH.read_text(encoding="utf-8")

    try:
        ai_decision = await classify_message(
            prompt=prompt,
            text=normalized.text,
            language=normalized.language,
            car_info=normalized.car_info,
            conversation_history=user.conversation_history,
        )
        return _stabilize_decision(normalized.text, user, ai_decision)
    except OpenAIRouterUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _stabilize_decision(text: str, user, decision: RouterDecision) -> RouterDecision:
    lowered = str(text or "").strip().lower()
    has_car = _has_car_hint(lowered)
    has_problem = _has_problem_hint(lowered)
    has_diagnostic_intent = _has_diagnostic_intent(lowered)
    has_helped = _has_feedback_helped(lowered)
    has_deep = _has_feedback_deep(lowered)
    is_greeting = _is_greeting(lowered)

    if is_greeting:
        if has_diagnostic_intent or has_problem or has_car:
            return decision.model_copy(
                update={
                    "message_type": "new_diagnostic",
                    "need_car_info": False,
                    "need_clarification": False,
                    "ready_to_search": True,
                    "deep_search": False,
                }
            )
        return decision.model_copy(
            update={
                "message_type": "general",
                "need_car_info": False,
                "ready_to_search": False,
                "deep_search": False,
            }
        )

    if has_deep:
        return decision.model_copy(
            update={
                "message_type": "followup_deep",
                "need_car_info": False,
                "ready_to_search": True,
                "deep_search": True,
                "response": decision.response or "Let's dig deeper.",
            }
        )

    if has_helped:
        return decision.model_copy(
            update={
                "message_type": "helped_feedback",
                "need_car_info": False,
                "ready_to_search": False,
                "deep_search": False,
                "response": decision.response or "Glad it helped.",
            }
        )

    if has_car and has_problem and decision.message_type in {"general", "clarification"}:
        return decision.model_copy(
            update={
                "message_type": "new_diagnostic",
                "need_car_info": False,
                "need_clarification": False,
                "ready_to_search": True,
                "deep_search": False,
            }
        )

    if has_diagnostic_intent and decision.message_type in {"general", "clarification"}:
        return decision.model_copy(
            update={
                "message_type": "new_diagnostic",
                "need_car_info": False,
                "need_clarification": False,
                "ready_to_search": True,
                "deep_search": False,
            }
        )

    if has_problem and decision.message_type == "clarification" and (getattr(user, "car_info", "") or decision.active_car):
        return decision.model_copy(
            update={
                "message_type": "new_diagnostic",
                "need_car_info": False,
                "need_clarification": False,
                "ready_to_search": True,
                "deep_search": False,
            }
        )

    return decision
