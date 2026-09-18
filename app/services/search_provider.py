from __future__ import annotations

import os
from typing import Callable

try:  # pragma: no cover - optional dependency in some local environments
    import anthropic  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    anthropic = None

try:  # pragma: no cover - optional dependency in some local environments
    from openai import OpenAI  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    OpenAI = None

from app.schemas.parser import DiagnosticRequest
from app.services.provider_config import (
    get_claude_search_model,
    get_openai_search_model,
    get_search_provider,
)


ORDINARY_MAX_OUTPUT_TOKENS = 1400
DEEP_MAX_OUTPUT_TOKENS = 2500
ORDINARY_WEB_SEARCH_USES = 2
DEEP_WEB_SEARCH_USES = 4


def _error_result(*, message: str, mode: str, allowed_domains: list[str], fallback_used: bool = False) -> dict:
    return {
        "error": message,
        "summary": "Сервис поиска временно недоступен. Повторите запрос позже.",
        "common_causes": [],
        "solutions": [],
        "topics_found": [],
        "links": [],
        "total_topics": 0,
        "confidence": "low",
        "recommendation": "",
        "need_more_info": False,
        "clarifying_question": "",
        "_meta": {
            "mode": mode,
            "allowed_domains": allowed_domains,
            "fallback_used": fallback_used,
            "version": "7.2",
        },
    }


def collect_response_text(response) -> str:
    parts = []
    for block in response.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)


def _field(value, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def collect_response_links(response) -> list[dict]:
    """Collect real provider-returned URLs without depending on prose JSON."""
    links: list[dict] = []
    seen: set[str] = set()

    def add(item) -> None:
        url = str(_field(item, "url", "") or "").strip()
        if not url or url in seen:
            return
        seen.add(url)
        links.append({
            "title": str(_field(item, "title", "") or url).strip(),
            "url": url,
            "description": str(
                _field(item, "description", "")
                or _field(item, "cited_text", "")
                or ""
            ).strip()[:600],
            "type": "link",
        })

    for block in (_field(response, "content", []) or []):
        for citation in (_field(block, "citations", []) or []):
            add(citation)
        content = _field(block, "content", []) or []
        if isinstance(content, (list, tuple)):
            for item in content:
                add(item)
                for citation in (_field(item, "citations", []) or []):
                    add(citation)
    return links


def response_telemetry(response) -> dict:
    usage = _field(response, "usage", None)
    telemetry = {
        "stop_reason": str(_field(response, "stop_reason", "") or ""),
    }
    for name in (
        "input_tokens", "output_tokens", "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ):
        value = _field(usage, name, None)
        if isinstance(value, int):
            telemetry[name] = value
    server_tools = _field(usage, "server_tool_use", None)
    if server_tools is not None:
        web_uses = _field(server_tools, "web_search_requests", None)
        if isinstance(web_uses, int):
            telemetry["web_search_requests"] = web_uses
    return {key: value for key, value in telemetry.items() if value not in (None, "")}


def unique_domains(domains: list[str]) -> list[str]:
    result = []
    seen = set()
    for domain in domains:
        normalized = str(domain or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def run_claude_search(client, data: DiagnosticRequest, user_message: str, domains: list[str], *, system_prompt: str):
    expanded = data.mode.lower() == "deep"
    return client.messages.create(
        model=get_claude_search_model(),
        max_tokens=DEEP_MAX_OUTPUT_TOKENS if expanded else ORDINARY_MAX_OUTPUT_TOKENS,
        system=system_prompt,
        tools=[
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": DEEP_WEB_SEARCH_USES if expanded else ORDINARY_WEB_SEARCH_USES,
                "allowed_domains": unique_domains(domains),
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )


def run_openai_search(client, data: DiagnosticRequest, user_message: str, domains: list[str], *, system_prompt: str):
    expanded = data.mode.lower() == "deep"
    return client.responses.create(
        model=get_openai_search_model(),
        instructions=system_prompt,
        input=user_message,
        max_output_tokens=DEEP_MAX_OUTPUT_TOKENS if expanded else ORDINARY_MAX_OUTPUT_TOKENS,
        tools=[
            {
                "type": "web_search_preview",
                "search_context_size": "high" if expanded else "medium",
            }
        ],
    )


def _run_claude_provider(
    *,
    data: DiagnosticRequest,
    user_message: str,
    allowed_domains: list[str],
    fallback_domains: list[str],
    system_prompt: str,
    extract_json: Callable[[str], dict],
) -> dict:
    mode = data.mode.lower().strip()
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or anthropic is None:
        return _error_result(
            message="ANTHROPIC_API_KEY not set" if not api_key else "anthropic package is not installed",
            mode=mode,
            allowed_domains=allowed_domains,
        )

    client = anthropic.Anthropic(api_key=api_key)
    used_domains = allowed_domains
    fallback_used = False
    try:
        try:
            response = run_claude_search(client, data, user_message, allowed_domains, system_prompt=system_prompt)
        except Exception as first_error:
            error_text = str(first_error).lower()
            domain_error = (
                "domains are not accessible" in error_text
                or "allowed_domains" in error_text
                or "invalid_request_error" in error_text
            )
            if not domain_error:
                raise
            used_domains = unique_domains(fallback_domains)
            fallback_used = True
            response = run_claude_search(client, data, user_message, used_domains, system_prompt=system_prompt)

        raw_text = collect_response_text(response)
        result = extract_json(raw_text)
        provider_links = collect_response_links(response)
        existing_links = result.get("links") if isinstance(result.get("links"), list) else []
        result["links"] = unique_links = []
        seen_urls: set[str] = set()
        for item in [*existing_links, *provider_links]:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            unique_links.append(item)
        result["_meta"] = {
            "engine": "Claude Haiku 4.5 + web_search",
            "mode": mode,
            "allowed_domains": used_domains,
            "fallback_used": fallback_used,
            "version": "7.2",
            "telemetry": response_telemetry(response),
        }
        return result
    except Exception as error:
        return _error_result(
            message=str(error),
            mode=mode,
            allowed_domains=used_domains,
            fallback_used=fallback_used,
        )


def _run_openai_provider(
    *,
    data: DiagnosticRequest,
    user_message: str,
    allowed_domains: list[str],
    system_prompt: str,
    search_hints: list[str],
    extract_json: Callable[[str], dict],
    result_matches_request: Callable[[dict, DiagnosticRequest], bool],
) -> dict:
    mode = data.mode.lower().strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if not openai_key or OpenAI is None:
        return _error_result(
            message="OPENAI_API_KEY not set" if not openai_key else "openai package is not installed",
            mode=mode,
            allowed_domains=allowed_domains,
        )

    try:
        openai_client = OpenAI(api_key=openai_key)
        attempt_messages = [user_message]
        if search_hints:
            attempt_messages.append(
                user_message
                + "\n\nStrict second pass for this request:\n- "
                + "\n- ".join(search_hints)
                + "\n- Return only links and conclusions that explicitly discuss the requested part."
            )

        last_result: dict | None = None
        for attempt_index, attempt_message in enumerate(attempt_messages, start=1):
            openai_response = run_openai_search(
                openai_client,
                data,
                attempt_message,
                allowed_domains,
                system_prompt=system_prompt,
            )
            openai_text = getattr(openai_response, "output_text", "") or ""
            openai_result = extract_json(openai_text)
            openai_result["_meta"] = {
                "engine": "OpenAI web_search",
                "mode": mode,
                "allowed_domains": allowed_domains,
                "fallback_used": False,
                "version": "7.4",
                "attempt": attempt_index,
            }
            last_result = openai_result
            if not openai_result.get("error") and result_matches_request(openai_result, data):
                return openai_result
        return _error_result(
            message="OpenAI search did not return a matching result",
            mode=mode,
            allowed_domains=allowed_domains,
        ) if last_result is None else last_result
    except Exception as error:
        return _error_result(
            message=str(error),
            mode=mode,
            allowed_domains=allowed_domains,
        )


def run_search_provider(
    *,
    data: DiagnosticRequest,
    user_message: str,
    allowed_domains: list[str],
    fallback_domains: list[str],
    system_prompt: str,
    search_hints: list[str],
    extract_json: Callable[[str], dict],
    result_matches_request: Callable[[dict, DiagnosticRequest], bool],
) -> dict:
    provider = get_search_provider()
    if provider == "claude":
        return _run_claude_provider(
            data=data,
            user_message=user_message,
            allowed_domains=allowed_domains,
            fallback_domains=fallback_domains,
            system_prompt=system_prompt,
            extract_json=extract_json,
        )
    if provider == "openai":
        return _run_openai_provider(
            data=data,
            user_message=user_message,
            allowed_domains=allowed_domains,
            system_prompt=system_prompt,
            search_hints=search_hints,
            extract_json=extract_json,
            result_matches_request=result_matches_request,
        )
    return _error_result(
        message=f"Unsupported SEARCH_PROVIDER: {provider}",
        mode=data.mode.lower().strip(),
        allowed_domains=allowed_domains,
    )
