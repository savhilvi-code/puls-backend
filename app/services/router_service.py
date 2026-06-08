from pathlib import Path

from fastapi import HTTPException

from app.schemas.router import RouterDecision
from app.services.openai_service import OpenAIRouterUnavailableError, classify_message
from app.utils.language import normalize_language_code

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "router_prompt.txt"


def _local_router(text: str, language: str) -> RouterDecision:
    lowered = text.lower().strip()
    language = normalize_language_code(language)

    positive = {"helped", "fixed", "solved", "works", "thanks"}
    negative = {"not helped", "did not help", "still", "deeper", "more details"}
    greetings = {"hi", "hello", "hey", "привет", "здравствуйте", "здравствуй"}

    if lowered in greetings or lowered.startswith(tuple(greetings)):
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
        return ai_decision
    except OpenAIRouterUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
