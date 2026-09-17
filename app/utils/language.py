import re


_WORD_RE = re.compile(r"[A-Za-z\u0400-\u04ff\u10a0-\u10ff0-9]+")


def normalize_language_code(language: str) -> str:
    value = str(language or "").strip().lower()
    if value.startswith("ru"):
        return "ru"
    if value.startswith("ka"):
        return "ka"
    return "en"


def detect_language(text: str, fallback: str = "en") -> str:
    """Detect prose language without treating technical tokens as English prose."""
    russian_words = 0
    english_words = 0
    georgian_words = 0

    for word in _WORD_RE.findall(str(text or "")):
        if any("\u0400" <= char <= "\u04ff" for char in word):
            russian_words += 1
            continue
        if any("\u10a0" <= char <= "\u10ff" for char in word):
            georgian_words += 1
            continue
        if not any("a" <= char.lower() <= "z" for char in word):
            continue

        letters = "".join(char for char in word if char.isalpha())
        is_technical = any(char.isdigit() for char in word) or (
            len(letters) >= 2 and letters.isupper()
        ) or (word[:1].isupper() and word[1:].islower())
        if not is_technical:
            english_words += 1

    if russian_words and russian_words >= english_words and russian_words >= georgian_words:
        return "ru"
    if georgian_words and georgian_words >= english_words:
        return "ka"
    if english_words:
        return "en"
    if russian_words:
        return "ru"
    if georgian_words:
        return "ka"
    return normalize_language_code(fallback)


def requested_response_language(text: str) -> str | None:
    """Return a language only for an explicit request to switch response language."""
    value = " ".join(str(text or "").lower().split())
    requests = (
        ("en", r"\b(?:ответь|отвечай|пиши|говори|перейди|продолжай)\b.{0,24}\b(?:на )?английск"),
        ("ru", r"\b(?:ответь|отвечай|пиши|говори|перейди|продолжай)\b.{0,24}\b(?:на )?русск"),
        ("en", r"\b(?:answer|reply|respond|write|speak|switch|continue)\b.{0,24}\benglish\b"),
        ("ru", r"\b(?:answer|reply|respond|write|speak|switch|continue)\b.{0,24}\brussian\b"),
    )
    for language, pattern in requests:
        if re.search(pattern, value):
            return language
    return None
