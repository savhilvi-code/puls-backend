def normalize_language_code(language: str) -> str:
    value = str(language or "").strip().lower()
    if value.startswith("ru"):
        return "ru"
    if value.startswith("ka"):
        return "ka"
    return "en"


def detect_language(text: str) -> str:
    text = str(text or "")
    if any("\u0400" <= char <= "\u04ff" for char in text):
        return "ru"
    return "en"

