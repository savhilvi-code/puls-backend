from __future__ import annotations

import re
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


def _clean_text(value: str, *, max_len: int = 1400) -> str:
    text = str(value or "").strip()
    text = re.sub(r"</?cite\b[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    if len(text) > max_len:
        text = text[:max_len].rstrip() + "..."
    return text


def _split_links(links: Iterable[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    forum_links = []
    youtube_links = []
    image_links = []
    for item in links or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        link_type = str(item.get("type") or "").strip().lower()
        if "youtube" in url.lower() or "youtu.be" in url.lower() or link_type == "video":
            target = youtube_links
            normalized_type = "video"
        elif link_type in {"image", "photo", "picture"}:
            target = image_links
            normalized_type = "image"
        else:
            target = forum_links
            normalized_type = "link"
        target.append({"title": title, "url": url, "description": description, "type": normalized_type})
    return forum_links, youtube_links, image_links


def format_technical_answer(*, language: str, diagnosis: str, probable_causes: list[str], first_checks: list[str], less_likely: list[str], links: list[dict], question_tail: str | None = None, additional_findings: list[str] | None = None, limitations: str = "") -> str:
    language = str(language or "en").lower()[:2]
    labels = {
        "ru": {
            "diagnosis": "Короткий диагноз",
            "causes": "Вероятные причины",
            "checks": "Что проверить сначала",
            "less": "Менее вероятные причины",
            "forum": "Форумы",
            "video": "YouTube",
            "images": "Изображения и схемы",
            "findings": "Дополнительные данные",
            "limitations": "Ограничения",
            "question": "Это помогло решить проблему? Если нет — напишите 'не помогло', и я запущу более глубокий поиск.",
        },
        "en": {
            "diagnosis": "Short diagnosis",
            "causes": "Likely causes",
            "checks": "Check first",
            "less": "Less likely causes",
            "forum": "Forums",
            "video": "YouTube",
            "images": "Images and diagrams",
            "findings": "Additional findings",
            "limitations": "Limitations",
            "question": "Did this solve the problem? If not, write 'not helped' and I will run a deeper search.",
        },
    }.get(language, {
        "diagnosis": "Short diagnosis",
        "causes": "Likely causes",
        "checks": "Check first",
        "less": "Less likely causes",
        "forum": "Forums",
        "video": "YouTube",
        "images": "Images and diagrams",
        "findings": "Additional findings",
        "limitations": "Limitations",
        "question": "Did this solve the problem? If not, write 'not helped' and I will run a deeper search.",
    })

    forum_links, youtube_links, image_links = _split_links(links)
    diagnosis = _clean_text(diagnosis, max_len=900)
    probable_causes = [_clean_text(item, max_len=260) for item in probable_causes]
    first_checks = [_clean_text(item, max_len=520) for item in first_checks]
    less_likely = [_clean_text(item, max_len=240) for item in less_likely]
    additional_findings = [_clean_text(item, max_len=420) for item in (additional_findings or [])]
    limitations = _clean_text(limitations, max_len=520)

    parts = [f"{labels['diagnosis']}: {diagnosis}".strip()]
    if probable_causes:
        parts.append(f"{labels['causes']}:\n- " + "\n- ".join(_dedupe(probable_causes)))
    if first_checks:
        parts.append(f"{labels['checks']}:\n- " + "\n- ".join(_dedupe(first_checks)))
    if less_likely:
        parts.append(f"{labels['less']}:\n- " + "\n- ".join(_dedupe(less_likely)))
    if additional_findings:
        parts.append(f"{labels['findings']}:\n- " + "\n- ".join(_dedupe(additional_findings)))
    if limitations:
        parts.append(f"{labels['limitations']}: {limitations}")
    if forum_links:
        forum_block = "\n".join(f"- {item['title']}: {item['url']}" for item in forum_links)
        parts.append(f"{labels['forum']}:\n{forum_block}")
    if youtube_links:
        youtube_block = "\n".join(f"- {item['title']}: {item['url']}" for item in youtube_links)
        parts.append(f"{labels['video']}:\n{youtube_block}")
    if image_links:
        image_block = "\n".join(f"- {item['title']}: {item['url']}" for item in image_links)
        parts.append(f"{labels['images']}:\n{image_block}")
    if question_tail is None:
        parts.append(labels["question"])
    elif question_tail:
        parts.append(question_tail.strip())
    return "\n\n".join(part for part in parts if part and part.strip())


def format_from_kb(*, language: str, answer: str, links: list[dict], question_tail: str | None = None) -> str:
    language = str(language or "en").lower()[:2]
    followup = question_tail or (
        "Это помогло решить проблему? Если нет — напишите 'не помогло', и я запущу более глубокий поиск."
        if language == "ru"
        else "Did this solve the problem? If not, write 'not helped' and I will run a deeper search."
    )
    answer = _clean_text(answer, max_len=2200)
    forum_links, youtube_links, image_links = _split_links(links)
    parts = [answer] if answer else []
    if forum_links:
        parts.append("Forums:\n" + "\n".join(f"- {item['title']}: {item['url']}" for item in forum_links))
    if youtube_links:
        parts.append("YouTube:\n" + "\n".join(f"- {item['title']}: {item['url']}" for item in youtube_links))
    if image_links:
        parts.append("Images:\n" + "\n".join(f"- {item['title']}: {item['url']}" for item in image_links))
    parts.append(followup)
    return "\n\n".join(parts)
