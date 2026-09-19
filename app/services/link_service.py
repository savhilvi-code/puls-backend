from __future__ import annotations

from app.services.trace_service import emit_event

VIDEO_DOMAINS = ("youtube.com", "youtu.be", "rutube.ru", "vimeo.com")
STORAGE_MEDIA_TYPES = {"photo", "video", "audio", "document"}
BRANDING_MARKERS = (
    "favicon", "site-logo", "site_logo", "puls-logo", "puls_logo",
    "brand-logo", "brand_logo", "avatar", "apple-touch-icon", "logo.svg",
    "logo.png", "logo.jpg", "logo.webp",
)


def normalize_media_type(provider_type: str) -> str:
    value = str(provider_type or "").strip().lower()
    if value in {"image", "img", "picture"}:
        return "photo"
    if value in {"webpage", "page", "manual", "link"}:
        return "document"
    if value in STORAGE_MEDIA_TYPES:
        return value
    return ""


def normalize_links(links: list[dict] | None) -> list[dict]:
    normalized: list[dict] = []
    seen: set[str] = set()
    for item in links or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("link") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        link_type = str(item.get("type") or "").strip().lower()
        if not link_type:
            link_type = "video" if any(domain in url.lower() for domain in VIDEO_DOMAINS) else "link"
        normalized.append(
            {
                "title": str(item.get("title") or item.get("forum") or item.get("name") or url).strip(),
                "url": url,
                "description": str(item.get("description") or item.get("key_info") or "").strip(),
                "type": link_type,
                "source_url": str(item.get("source_url") or item.get("source_page_url") or "").strip(),
            }
        )
    return normalized


def is_branding_asset(item: dict) -> bool:
    blob = " ".join(
        str(item.get(key) or "").lower()
        for key in ("url", "title", "description")
    )
    title_words = {
        "".join(char for char in word.lower() if char.isalnum())
        for word in str(item.get("title") or "").split()
    }
    return any(marker in blob for marker in BRANDING_MARKERS) or bool(
        title_words & {"logo", "branding", "favicon", "avatar"}
    )


def sanitize_search_links(
    links: list[dict] | None,
    *,
    query: str = "",
    visual_requested: bool = False,
) -> list[dict]:
    """Reject branding masquerading as evidence and keep visual provenance."""
    normalized = normalize_links(links)
    query_terms = {
        "".join(char for char in token.lower() if char.isalnum())
        for token in str(query or "").split()
        if len("".join(char for char in token if char.isalnum())) >= 4
    }
    result: list[dict] = []
    retained_urls: set[str] = set()

    def retain_source_page(item: dict) -> None:
        source_url = str(item.get("source_url") or "").strip()
        if (
            not source_url
            or source_url == str(item.get("url") or "").strip()
            or source_url in retained_urls
            or any(marker in source_url.lower() for marker in BRANDING_MARKERS)
        ):
            return
        retained_urls.add(source_url)
        result.append({
            "title": "Source page" if is_branding_asset(item) else str(item.get("title") or "Source page").strip(),
            "url": source_url,
            "description": str(item.get("description") or "").strip(),
            "type": "link",
            "source_url": "",
        })

    for item in normalized:
        image = str(item.get("type") or "").lower() in {"image", "photo", "picture"}
        if image:
            emit_event("IMAGE", module="link_service", operation="RESULT", from_node="Sources", to_node="Image Candidates", edge_label="CANDIDATE", output_data={**item, "state": "candidate"})
        if image and is_branding_asset(item):
            emit_event("IMAGE", module="link_service", operation="VERIFY", status="SKIPPED", from_node="Image Candidates", to_node="Rejected Images", edge_label="BRANDING_ASSET", output_data={**item, "state": "rejected", "reason": "branding_asset"})
            retain_source_page(item)
            continue
        if image and visual_requested and query_terms:
            blob = " ".join(
                str(item.get(key) or "").lower()
                for key in ("url", "title", "description", "source_url")
            )
            if not any(term in blob for term in query_terms):
                emit_event("IMAGE", module="link_service", operation="VERIFY", status="SKIPPED", from_node="Image Candidates", to_node="Rejected Images", edge_label="QUERY_MISMATCH", output_data={**item, "state": "rejected", "reason": "query_mismatch"})
                retain_source_page(item)
                continue
        if image:
            emit_event("IMAGE", module="link_service", operation="VERIFY", from_node="Image Candidates", to_node="Selected Images", edge_label="SELECTED", output_data={**item, "state": "selected"})
        if item["url"] not in retained_urls:
            retained_urls.add(item["url"])
            result.append(item)
    return result


def extract_videos(links: list[dict] | None) -> list[dict]:
    return [
        item
        for item in normalize_links(links)
        if item.get("type") == "video" or any(domain in item.get("url", "").lower() for domain in VIDEO_DOMAINS)
    ]
