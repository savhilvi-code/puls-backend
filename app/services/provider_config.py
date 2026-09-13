import os


DEFAULT_SEARCH_PROVIDER = "claude"
DEFAULT_DIAGNOSTIC_PROVIDER = "none"
DEFAULT_CLAUDE_SEARCH_MODEL = "claude-haiku-4-5"
DEFAULT_OPENAI_SEARCH_MODEL = "gpt-4.1-mini"
DEFAULT_OPENAI_DIAGNOSTIC_MODEL = ""


def get_search_provider() -> str:
    provider = os.getenv("SEARCH_PROVIDER", DEFAULT_SEARCH_PROVIDER).strip().lower()
    return provider or DEFAULT_SEARCH_PROVIDER


def get_diagnostic_provider() -> str:
    provider = os.getenv("DIAGNOSTIC_PROVIDER", DEFAULT_DIAGNOSTIC_PROVIDER).strip().lower()
    return provider or DEFAULT_DIAGNOSTIC_PROVIDER


def get_claude_search_model() -> str:
    model = os.getenv("CLAUDE_SEARCH_MODEL", DEFAULT_CLAUDE_SEARCH_MODEL).strip()
    return model or DEFAULT_CLAUDE_SEARCH_MODEL


def get_openai_search_model() -> str:
    model = os.getenv("OPENAI_SEARCH_MODEL", DEFAULT_OPENAI_SEARCH_MODEL).strip()
    return model or DEFAULT_OPENAI_SEARCH_MODEL


def get_openai_diagnostic_model() -> str:
    model = os.getenv("OPENAI_DIAGNOSTIC_MODEL", DEFAULT_OPENAI_DIAGNOSTIC_MODEL).strip()
    return model or DEFAULT_OPENAI_DIAGNOSTIC_MODEL
