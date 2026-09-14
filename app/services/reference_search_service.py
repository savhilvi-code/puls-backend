from __future__ import annotations

import json

from app.schemas.parser import DiagnosticRequest
from app.services.parser_engine import build_allowed_domains, extract_json
from app.services.search_provider import run_search_provider


class ReferenceSearchUnavailableError(RuntimeError):
    pass


def _reference_prompt(intent: str) -> str:
    return (
        "You are PULS reference search. Find real, reusable automotive reference links for the user's current subject. "
        "Do not diagnose unless the intent is diagnostic. Do not invent URLs. Prefer stable source pages, manuals, images, "
        "and real video pages. Return only valid JSON with keys: summary, links, confidence. "
        "Each link must include title, url, description, and type. Type must be one of link, image, video, manual. "
        f"Current search intent: {intent}."
    )


def _reference_user_message(
    *,
    active_vehicle: str,
    current_subject: str,
    reference_target: str,
    user_text: str,
    language: str,
) -> str:
    payload = {
        "active_vehicle": active_vehicle,
        "current_subject": current_subject,
        "reference_target": reference_target,
        "user_text": user_text,
        "language": language,
        "instructions": [
            "Keep the result tied to the current subject and reference target.",
            "For video requests, prefer youtube.com or youtu.be links when available.",
            "For image requests, return source page URLs and direct image URLs only if they are present in search results.",
            "Discard noisy results that are not clearly relevant.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def _normalize_reference_links(raw_links) -> list[dict]:
    if isinstance(raw_links, dict):
        raw_links = raw_links.get("links") or raw_links.get("items") or []
    if not isinstance(raw_links, list):
        return []

    links: list[dict] = []
    seen: set[str] = set()
    for item in raw_links:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("link") or "").strip()
        if not url or url in seen or not url.startswith(("http://", "https://")):
            continue
        seen.add(url)
        link_type = str(item.get("type") or "").strip().lower()
        if link_type not in {"link", "image", "video", "manual"}:
            lowered = url.lower()
            link_type = "video" if any(host in lowered for host in ("youtube.com", "youtu.be", "rutube.ru", "vimeo.com")) else "link"
        links.append(
            {
                "title": str(item.get("title") or item.get("name") or url).strip(),
                "url": url,
                "description": str(item.get("description") or item.get("snippet") or "").strip(),
                "type": link_type,
            }
        )
    return links


async def search_reference(
    *,
    active_vehicle: str,
    current_subject: str,
    reference_target: str,
    user_text: str,
    language: str,
    intent: str,
) -> dict:
    query = " ".join(part for part in (active_vehicle, reference_target, current_subject, user_text) if part).strip()
    if not query:
        raise ReferenceSearchUnavailableError("Reference search query is empty.")

    data = DiagnosticRequest(
        query=query,
        lang=language or "en",
        car_info=active_vehicle,
        conversation_history="",
        mode="normal",
    )
    result = run_search_provider(
        data=data,
        user_message=_reference_user_message(
            active_vehicle=active_vehicle,
            current_subject=current_subject,
            reference_target=reference_target,
            user_text=user_text,
            language=language,
        ),
        allowed_domains=build_allowed_domains(data),
        fallback_domains=["youtube.com", "youtu.be", "manualslib.com", "charm.li", "autozone.com"],
        system_prompt=_reference_prompt(intent),
        search_hints=[],
        extract_json=extract_json,
        result_matches_request=lambda candidate, _data: bool(_normalize_reference_links(candidate.get("links"))),
    )
    links = _normalize_reference_links(result.get("links"))
    if not links and isinstance(result.get("topics_found"), list):
        links = _normalize_reference_links(result.get("topics_found"))
    if not links:
        raise ReferenceSearchUnavailableError(str(result.get("error") or "Reference search returned no usable links."))
    return {
        "summary": str(result.get("summary") or result.get("recommendation") or "").strip(),
        "links": links,
        "raw": result,
    }
