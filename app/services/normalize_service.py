from app.schemas.chat import NormalizedInput
from app.utils.language import detect_language


def normalize_chat_input(payload: dict, source: str | None = None) -> NormalizedInput:
    text = str(payload.get("text") or payload.get("message") or "").strip()
    language = str(payload.get("language") or "").strip().lower()
    language = language or detect_language(text)

    return NormalizedInput(
        source=str(source or payload.get("source") or "web"),
        text=text,
        auth_user_id=str(payload.get("auth_user_id") or ""),
        telegram_id=str(payload.get("telegram_id") or ""),
        chat_id=str(payload.get("chat_id") or ""),
        email=str(payload.get("email") or ""),
        username=str(payload.get("username") or ""),
        first_name=str(payload.get("first_name") or ""),
        car_info=str(payload.get("car_info") or ""),
        language=language,
    )

