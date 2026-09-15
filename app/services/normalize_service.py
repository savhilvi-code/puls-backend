from app.schemas.chat import NormalizedInput
from app.utils.language import detect_language


def normalize_chat_input(payload: dict, source: str | None = None) -> NormalizedInput:
    text = str(payload.get("text") or payload.get("message") or "").strip()
    language = str(payload.get("language") or "").strip().lower()
    language = language or detect_language(text)

    return NormalizedInput(
        source=str(source or payload.get("source") or "web"),
        text=text,
        language=language,
        conversation_id=payload.get("conversation_id"),
        vehicle_id=payload.get("vehicle_id"),
        problem_id=payload.get("problem_id"),
    )
