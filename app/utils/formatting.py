from app.schemas.chat import LinkItem
from app.utils.language import normalize_language_code


def build_answer_payload(*, answer: str, links: list[dict] | list[LinkItem], language: str) -> dict:
    normalized_links = []
    for item in links or []:
        if isinstance(item, LinkItem):
            normalized_links.append(item.model_dump())
        elif isinstance(item, dict):
            normalized_links.append(
                {
                    "title": str(item.get("title", "")),
                    "url": str(item.get("url", "")),
                    "description": str(item.get("description", "")),
                    "type": str(item.get("type", "link")),
                }
            )
    return {
        "answer": str(answer or "").strip(),
        "links": normalized_links,
        "language": normalize_language_code(language),
    }

