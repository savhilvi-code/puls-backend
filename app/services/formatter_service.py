from __future__ import annotations

from typing import Iterable


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        value = str(item or "").strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _split_links(links: Iterable[dict]) -> tuple[list[dict], list[dict]]:
    forum_links = []
    youtube_links = []
    for item in links or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        link_type = str(item.get("type") or "").strip().lower()
        target = youtube_links if ("youtube" in url.lower() or "youtu.be" in url.lower() or link_type == "video") else forum_links
        target.append({"title": title, "url": url, "description": description, "type": "video" if target is youtube_links else "link"})
    return forum_links, youtube_links


def format_technical_answer(*, language: str, diagnosis: str, probable_causes: list[str], first_checks: list[str], less_likely: list[str], links: list[dict], question_tail: str) -> str:
    language = str(language or "en").lower()[:2]
    labels = {
        "ru": {
            "diagnosis": "Короткий диагноз",
            "causes": "Вероятные причины",
            "checks": "Что проверить сначала",
            "less": "Менее вероятные причины",
            "forum": "Форумы",
            "video": "YouTube",
            "question": "Это помогло решить проблему? Если нет — напишите 'не помогло', и я запущу более глубокий поиск.",
        },
        "en": {
            "diagnosis": "Short diagnosis",
            "causes": "Likely causes",
            "checks": "Check first",
            "less": "Less likely causes",
            "forum": "Forums",
            "video": "YouTube",
            "question": "Did this solve the problem? If not, write 'not helped' and I will run a deeper search.",
        },
    }.get(language, {
        "diagnosis": "Short diagnosis",
        "causes": "Likely causes",
        "checks": "Check first",
        "less": "Less likely causes",
        "forum": "Forums",
        "video": "YouTube",
        "question": "Did this solve the problem? If not, write 'not helped' and I will run a deeper search.",
    })

    forum_links, youtube_links = _split_links(links)
    parts = [
        f"{labels['diagnosis']}: {diagnosis}".strip(),
    ]
    if probable_causes:
        parts.append(f"{labels['causes']}:\n- " + "\n- ".join(_dedupe(probable_causes)))
    if first_checks:
        parts.append(f"{labels['checks']}:\n- " + "\n- ".join(_dedupe(first_checks)))
    if less_likely:
        parts.append(f"{labels['less']}:\n- " + "\n- ".join(_dedupe(less_likely)))
    if forum_links:
        forum_block = "\n".join(f"- {item['title']}: {item['url']}" for item in forum_links)
        parts.append(f"{labels['forum']}:\n{forum_block}")
    if youtube_links:
        youtube_block = "\n".join(f"- {item['title']}: {item['url']}" for item in youtube_links)
        parts.append(f"{labels['video']}:\n{youtube_block}")
    if question_tail:
        parts.append(question_tail.strip())
    else:
        parts.append(labels["question"])
    return "\n\n".join(part for part in parts if part and part.strip())


def format_from_kb(*, language: str, answer: str, links: list[dict], question_tail: str | None = None) -> str:
    language = str(language or "en").lower()[:2]
    followup = question_tail or (
        "Это помогло решить проблему? Если нет — напишите 'не помогло', и я запущу более глубокий поиск."
        if language == "ru"
        else "Did this solve the problem? If not, write 'not helped' and I will run a deeper search."
    )
    answer = str(answer or "").strip()
    forum_links, youtube_links = _split_links(links)
    parts = [answer] if answer else []
    if forum_links:
        parts.append("Forums:\n" + "\n".join(f"- {item['title']}: {item['url']}" for item in forum_links))
    if youtube_links:
        parts.append("YouTube:\n" + "\n".join(f"- {item['title']}: {item['url']}" for item in youtube_links))
    parts.append(followup)
    return "\n\n".join(parts)

