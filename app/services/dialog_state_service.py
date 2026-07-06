from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.schemas.router import RouterDecision
from app.schemas.user import UserRecord


@dataclass
class DialogState:
    source: str
    message_type: str
    language: str
    active_car: str
    previous_symptom: str
    current_symptom: str
    needs_car_clarification: bool
    needs_problem_clarification: bool
    is_continuation: bool
    is_greeting: bool
    is_feedback_helped: bool
    is_feedback_not_helped: bool
    should_search: bool
    should_deep_search: bool


def _extract_last_value(history: str, key: str) -> str:
    lines = [line.strip() for line in str(history or "").splitlines() if line.strip()]
    for line in reversed(lines):
        if line.lower().startswith(f"{key.lower()}:"):
            return line.split(":", 1)[1].strip()
    return ""


def _extract_last_block_value(history: str, key: str) -> str:
    blocks = [block.strip() for block in str(history or "").split("\n---\n") if block.strip()]
    for block in reversed(blocks):
        value = _extract_last_value(block, key)
        if value:
            return value
    return ""


def _looks_like_diagnostic_intent(text: str) -> bool:
    lowered = str(text or '').strip().lower()
    return any(
        token in lowered
        for token in (
            'как заменить',
            'как поменять',
            'как снять',
            'как починить',
            'почему',
            'не работает',
            'не заводится',
            'теряет тягу',
            'нет тяги',
            'тупит',
            'дергается',
            'стучит',
            'свистит',
            'дымит',
            'горит',
            'шум',
            'ошибк',
            'диагност',
            'ремонт',
            'проверить',
            'устранить',
            'заменить',
            'поменять',
            'починить',
            'turbo',
            'stall',
            'stalls',
            'loss of power',
            'how to',
            'replace',
            'adjust',
            'tune',
            'fix',
            'repair',
            'change',
            'remove',
            'install',
            'service',
            'set up',
        )
    )


def _looks_like_greeting(text: str) -> bool:
    lowered = str(text or '').strip().lower()
    greetings = {
        'hi',
        'hello',
        'hey',
        'привет',
        'здравствуй',
        'здравствуйте',
        'добрый день',
        'доброе утро',
        'добрый вечер',
    }
    if lowered in greetings:
        return True
    if any(lowered == f'{token}!' or lowered == f'{token}.' or lowered == f'{token}?' for token in greetings):
        return True
    if any(lowered.startswith(token + ' ') for token in greetings):
        rest = lowered.split(' ', 1)[1].strip(' \\t\\n\\r,.:;!?')
        if _looks_like_diagnostic_intent(rest):
            return False
        return len(rest) <= 20
    return False


def _looks_like_helped(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    return lowered in {"helped", "fixed", "solved", "works", "помогло", "исправлено", "решено", "работает"}


def _looks_like_not_helped(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    phrases = {"не помогло", "ищи глубже", "нужно больше информации", "more details", "not helped", "still"}
    return any(phrase in lowered for phrase in phrases)


def _looks_like_car_info(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(token in lowered for token in ["nissan", "toyota", "honda", "bmw", "audi", "volkswagen", "vw", "ford", "mazda", "xtrail", "x-trail"])


def _looks_like_problem_text(text: str) -> bool:
    lowered = str(text or "").lower()
    keywords = [
        "плохо",
        "не работает",
        "не заводится",
        "не едет",
        "заводится",
        "холодную",
        "cold",
        "stall",
        "stalls",
        "noise",
        "noise",
        "свист",
        "стук",
        "вибрац",
        "ошиб",
        "loss of power",
        "turbo",
        "will not move",
        "won't move",
        "does not move",
        "doesn't move",
        "not move",
        "no movement",
        "won't start",
        "doesn't start",
        "no power",
        "loses power",
        "won't go",
        "will not move",
        "won't move",
        "does not move",
        "doesn't move",
        "not move",
        "no movement",
        "won't start",
        "doesn't start",
        "no power",
        "loses power",
        "won't go",
    ]
    return any(token in lowered for token in keywords)


def _looks_like_problem_text_extended(text: str) -> bool:
    lowered = str(text or "").lower()
    extra_keywords = [
        "теряет тягу",
        "потеря тяги",
        "нет тяги",
        "не тянет",
        "тупит",
        "дергается",
        "провал",
        "мощност",
        "разгон",
        "на прогретую",
        "на горячую",
        "на холодную",
        "теряет мощность",
    ]
    return any(token in lowered for token in extra_keywords)


def build_dialog_state(normalized, user: UserRecord, decision: RouterDecision) -> DialogState:
    current_text = str(normalized.text or "").strip()
    history = str(user.conversation_history or "")

    history_active_car = _extract_last_block_value(history, "active_car") or user.car_info
    history_symptom = _extract_last_block_value(history, "symptom")

    followup_uses_history_first = (
        _looks_like_helped(current_text)
        or _looks_like_not_helped(current_text)
        or decision.message_type in {"followup", "followup_deep", "helped_feedback"}
        or decision.user_says_helped
        or decision.user_says_not_helped
    )
    active_car = str(decision.active_car or "").strip()
    if not active_car:
        if followup_uses_history_first:
            active_car = str(history_active_car or normalized.car_info or user.car_info or "").strip()
        else:
            active_car = str(normalized.car_info or history_active_car or user.car_info or "").strip()
    if not active_car and _looks_like_car_info(current_text):
        active_car = current_text

    previous_symptom = history_symptom
    if decision.message_type == "followup_deep" and not previous_symptom:
        previous_symptom = _extract_last_block_value(history, "symptom")

    is_greeting = _looks_like_greeting(current_text)
    is_feedback_helped = _looks_like_helped(current_text) or decision.message_type == "helped_feedback" or decision.user_says_helped
    is_feedback_not_helped = _looks_like_not_helped(current_text) or decision.message_type == "followup_deep" or decision.user_says_not_helped
    is_continuation = bool(history_active_car or history_symptom) and not is_greeting

    has_clear_diagnostic_intent = bool(
        _looks_like_problem_text(current_text)
        or _looks_like_problem_text_extended(current_text)
        or _looks_like_diagnostic_intent(current_text)
    )

    needs_car_clarification = bool(
        (decision.need_car_info or decision.need_clarification)
        and not active_car
        and not is_greeting
        and not is_feedback_helped
        and not is_feedback_not_helped
        and not has_clear_diagnostic_intent
    )

    should_search = decision.message_type in {"new_diagnostic", "followup", "followup_deep"} and decision.ready_to_search
    should_deep_search = decision.deep_search or decision.message_type == "followup_deep" or is_feedback_not_helped

    if should_deep_search and not previous_symptom:
        previous_symptom = current_text

    needs_problem_clarification = bool(
        active_car
        and not is_greeting
        and not is_feedback_helped
        and not is_feedback_not_helped
        and not has_clear_diagnostic_intent
    )

    return DialogState(
        source=str(normalized.source or "web"),
        message_type=decision.message_type,
        language=str(decision.language or normalized.language or "en"),
        active_car=active_car,
        previous_symptom=previous_symptom,
        current_symptom=current_text,
        needs_car_clarification=needs_car_clarification,
        needs_problem_clarification=needs_problem_clarification,
        is_continuation=is_continuation,
        is_greeting=is_greeting,
        is_feedback_helped=is_feedback_helped,
        is_feedback_not_helped=is_feedback_not_helped,
        should_search=should_search,
        should_deep_search=should_deep_search,
    )


def history_context_block(*, source: str, message_type: str, active_car: str, symptom: str, user_text: str, assistant_text: str, links: Iterable[dict] | None = None) -> str:
    link_lines = []
    for item in links or []:
        if isinstance(item, dict):
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            if title and url:
                link_lines.append(f"- {title}: {url}")
            elif url:
                link_lines.append(f"- {url}")
    lines = [
        "---",
        f"source: {source}",
        f"message_type: {message_type}",
        f"active_car: {active_car}",
        f"symptom: {symptom}",
        f"user: {user_text}",
        f"assistant: {assistant_text}",
    ]
    if link_lines:
        lines.append("links:")
        lines.extend(link_lines)
    return "\n".join(lines)
