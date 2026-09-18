from __future__ import annotations

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
    for item in normalized:
        image = str(item.get("type") or "").lower() in {"image", "photo", "picture"}
        if image and is_branding_asset(item):
            continue
        if image and visual_requested and query_terms:
            blob = " ".join(
                str(item.get(key) or "").lower()
                for key in ("url", "title", "description", "source_url")
            )
            if not any(term in blob for term in query_terms):
                continue
        result.append(item)
    return result


def extract_videos(links: list[dict] | None) -> list[dict]:
    return [
        item
        for item in normalize_links(links)
        if item.get("type") == "video" or any(domain in item.get("url", "").lower() for domain in VIDEO_DOMAINS)
    ]
