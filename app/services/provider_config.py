import os


DEFAULT_SEARCH_PROVIDER = "claude"
DEFAULT_CLAUDE_SEARCH_MODEL = "claude-haiku-4-5"
DEFAULT_OPENAI_SEARCH_MODEL = "gpt-4.1-mini"


def get_search_provider() -> str:
    provider = os.getenv("SEARCH_PROVIDER", DEFAULT_SEARCH_PROVIDER).strip().lower()
    return provider or DEFAULT_SEARCH_PROVIDER


def get_claude_search_model() -> str:
    model = os.getenv("CLAUDE_SEARCH_MODEL", DEFAULT_CLAUDE_SEARCH_MODEL).strip()
    return model or DEFAULT_CLAUDE_SEARCH_MODEL


def get_openai_search_model() -> str:
    model = os.getenv("OPENAI_SEARCH_MODEL", DEFAULT_OPENAI_SEARCH_MODEL).strip()
    return model or DEFAULT_OPENAI_SEARCH_MODEL
