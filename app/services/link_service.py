from __future__ import annotations

VIDEO_DOMAINS = ("youtube.com", "youtu.be", "rutube.ru", "vimeo.com")


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
            }
        )
    return normalized


def extract_videos(links: list[dict] | None) -> list[dict]:
    return [
        item
        for item in normalize_links(links)
        if item.get("type") == "video" or any(domain in item.get("url", "").lower() for domain in VIDEO_DOMAINS)
    ]
