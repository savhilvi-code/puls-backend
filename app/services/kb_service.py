import re
from difflib import SequenceMatcher

from fastapi import HTTPException

from app.database.supabase import (
    SupabaseOperationError,
    SupabaseUnavailableError,
    create_knowledge_case,
    create_knowledge_event,
    get_supabase_client,
)
from app.services.formatter_service import format_from_kb
from app.services.parser_engine import extract_json


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def _tokenize(value: str) -> list[str]:
    return [
        token
        for token in _normalize_text(value)
        .replace("/", " ")
        .replace("-", " ")
        .split()
        if len(token) > 3
    ]


def _token_similar(a: str, b: str) -> bool:
    left = _normalize_text(a)
    right = _normalize_text(b)
    if not left or not right:
        return False
    if left == right or left in right or right in left:
        return True
    return SequenceMatcher(None, left, right).ratio() >= 0.82


def _contains_any(haystack: str, needle: str) -> bool:
    hay = _normalize_text(haystack)
    need = _normalize_text(needle)
    return bool(need) and need in hay


_KNOWN_BRANDS = (
    "toyota",
    "nissan",
    "honda",
    "mazda",
    "subaru",
    "mitsubishi",
    "suzuki",
    "lexus",
    "infiniti",
    "bmw",
    "mercedes",
    "audi",
    "volkswagen",
    "peugeot",
    "renault",
    "ford",
    "chevrolet",
    "hyundai",
    "kia",
)


def _vehicle_tokens(value: str) -> set[str]:
    text = _normalize_text(value)
    tokens = set(_tokenize(text))
    for brand in _KNOWN_BRANDS:
        if brand in text:
            tokens.add(brand)
    for match in re.findall(r"\b(19[8-9]\d|20[0-3]\d|[a-z0-9]{1,4}[- ]?[a-z]{2,4}|gs\d{3}|sr20vet|1g[- ]?gze)\b", text):
        tokens.add(match.replace(" ", "-"))
        tokens.add(match.replace("-", ""))
    return {token for token in tokens if len(token) > 2}


def _vehicle_context_matches(haystack: str, active_car: str) -> bool:
    active = _normalize_text(active_car)
    if not active:
        return True

    hay = _normalize_text(haystack)
    active_brands = {brand for brand in _KNOWN_BRANDS if brand in active}
    hay_brands = {brand for brand in _KNOWN_BRANDS if brand in hay}
    if active_brands:
        if not any(brand in hay for brand in active_brands):
            return False
        if hay_brands and not active_brands.intersection(hay_brands):
            return False

    critical_tokens = {
        token
        for token in _vehicle_tokens(active)
        if token in active_brands or re.search(r"\d", token) or len(token) >= 5
    }
    if critical_tokens:
        matched = sum(1 for token in critical_tokens if token in hay or token.replace("-", "") in hay.replace("-", ""))
        return matched >= min(2, len(critical_tokens))
    return True


def _normalize_link_item(item: dict) -> dict:
    return {
        "title": str(item.get("title") or item.get("forum") or item.get("name") or item.get("source") or ""),
        "url": str(item.get("url") or item.get("link") or ""),
        "description": str(item.get("description") or item.get("key_info") or item.get("summary") or ""),
        "type": str(item.get("type") or ("video" if any(domain in str(item.get("url") or "").lower() for domain in ("youtube.com", "youtu.be", "rutube.ru", "vimeo.com")) else "link")),
    }


def _normalize_links(raw_links) -> list[dict]:
    if isinstance(raw_links, dict):
        raw_links = raw_links.get("links") or raw_links.get("forum_links") or raw_links.get("items") or []
    if not isinstance(raw_links, list):
        return []

    normalized: list[dict] = []
    seen: set[str] = set()
    for item in raw_links:
        if not isinstance(item, dict):
            continue
        normalized_item = _normalize_link_item(item)
        url = normalized_item.get("url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        normalized.append(normalized_item)
    return normalized


def _row_links(row: dict) -> list[dict]:
    links = _normalize_links(row.get("forum_links") or [])
    if links:
        return links
    raw_payload = row.get("raw_payload") or {}
    if isinstance(raw_payload, dict):
        links = _normalize_links(raw_payload.get("links") or raw_payload.get("forum_links") or [])
        if links:
            return links
        topics = raw_payload.get("topics_found") or raw_payload.get("topics") or []
        if isinstance(topics, list):
            normalized: list[dict] = []
            for item in topics:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "").strip()
                title = str(item.get("title") or item.get("forum") or "").strip()
                if not url and not title:
                    continue
                normalized.append(
                    {
                        "title": title or url,
                        "url": url,
                        "description": str(item.get("key_info") or item.get("description") or ""),
                        "type": "video" if any(domain in url.lower() for domain in ("youtube.com", "youtu.be", "rutube.ru", "vimeo.com")) else "link",
                    }
                )
            if normalized:
                return normalized
    return [] 


def _diagnostic_vehicle_label(diagnostic_request: dict | None, active_car: str = "") -> str:
    row = diagnostic_request or {}
    parts = [
        str(row.get("brand") or "").strip(),
        str(row.get("model") or "").strip(),
        str(row.get("year") or "").strip(),
        str(row.get("engine") or "").strip(),
    ]
    label = " ".join(part for part in parts if part).strip()
    if label:
        return label
    return str(active_car or "").strip()


def _log_confirmed_knowledge_event(*, diagnostic_request: dict | None, vehicle_label: str, answer: str, language: str, result: str) -> None:
    row = diagnostic_request or {}
    symptom = str(
        row.get("raw_question")
        or row.get("question")
        or row.get("symptoms")
        or ""
    ).strip()
    if not symptom:
        return
    payload = {
        "country": language,
        "symptom": symptom[:1000],
        "cause": vehicle_label[:1000] if vehicle_label else None,
        "solution": answer[:4000] if answer else None,
        "result": result,
        "source": "confirmed_feedback",
    }
    try:
        create_knowledge_event(payload)
    except (SupabaseUnavailableError, SupabaseOperationError):
        return


def _knowledge_case_rows(client) -> list[dict]:
    response = client.table("knowledge_cases").select(
        "id,symptom_title,symptom_description,confirmed_cause,recommended_action,country,source_type,success_count,confidence,full_answer,raw_payload,forum_links"
    ).order("success_count", desc=True).limit(100).execute()
    rows = getattr(response, "data", []) or []
    for row in rows:
        row["source_table"] = "knowledge_cases"
    return rows


def _solved_case_rows(client) -> list[dict]:
    response = client.table("solved_cases").select(
        "id,brand,model,year,engine,symptoms,confirmed_problem,confirmed_solution,sources,videos,confidence,created_at"
    ).order("created_at", desc=True).limit(100).execute()
    rows = getattr(response, "data", []) or []
    normalized: list[dict] = []
    for row in rows:
        title = " ".join(
            str(row.get(key) or "").strip()
            for key in ("brand", "model", "year", "engine")
            if str(row.get(key) or "").strip()
        ).strip()
        normalized.append(
            {
                "id": row.get("id"),
                "symptom_title": title,
                "symptom_description": str(row.get("symptoms") or ""),
                "confirmed_cause": str(row.get("confirmed_problem") or ""),
                "recommended_action": str(row.get("confirmed_solution") or ""),
                "country": "",
                "source_type": "solved_case",
                "success_count": 1,
                "confidence": float(row.get("confidence") or 0.7),
                "full_answer": str(row.get("confirmed_solution") or ""),
                "raw_payload": row,
                "forum_links": row.get("sources") or [],
                "source_table": "solved_cases",
            }
        )
    return normalized


def _extract_embedded_case(text: str) -> dict:
    value = str(text or "").strip()
    if "{" not in value or "}" not in value:
        return {}
    parsed = extract_json(value)
    if not isinstance(parsed, dict):
        return {}
    if not any(parsed.get(field) for field in ("summary", "recommendation", "common_causes", "solutions", "links", "topics_found")):
        return {}
    return parsed


def _answer_from_structured_payload(payload: dict) -> str:
    summary = str(payload.get("summary") or payload.get("recommendation") or "").strip()
    causes = payload.get("common_causes") if isinstance(payload.get("common_causes"), list) else []
    solutions = payload.get("solutions") if isinstance(payload.get("solutions"), list) else []

    parts = [summary] if summary else []
    for item in causes[:2]:
        if isinstance(item, dict) and str(item.get("cause") or "").strip():
            parts.append(str(item.get("cause") or "").strip())
    for item in solutions[:2]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        step = "\n".join(part for part in (title, description) if part)
        if step:
            parts.append(step)
    return "\n\n".join(part for part in parts if part).strip()


def _jsonish_values(text: str, key: str, limit: int = 4) -> list[str]:
    values = []
    pattern = rf'"{re.escape(key)}"\s*:\s*"((?:[^"\\]|\\.)*)"'
    for match in re.finditer(pattern, str(text or ""), flags=re.IGNORECASE):
        value = match.group(1).replace('\\"', '"').replace("\\n", "\n").strip()
        if value and value not in values:
            values.append(value)
        if len(values) >= limit:
            break
    return values


def _clean_jsonish_answer(answer: str) -> tuple[str, list[dict]]:
    text = str(answer or "").strip()
    if '"summary"' not in text and '"common_causes"' not in text and '"solutions"' not in text:
        return text, []

    parts: list[str] = []
    summary = _jsonish_values(text, "summary", limit=1)
    recommendation = _jsonish_values(text, "recommendation", limit=1)
    causes = _jsonish_values(text, "cause", limit=2)
    titles = _jsonish_values(text, "title", limit=6)
    descriptions = _jsonish_values(text, "description", limit=6)

    parts.extend(summary or recommendation)
    parts.extend(causes)
    for title, description in zip(titles[:3], descriptions[:3]):
        if title.startswith("http"):
            continue
        parts.append("\n".join(part for part in (title, description) if part).strip())

    urls = _jsonish_values(text, "url", limit=10)
    links = []
    for index, url in enumerate(urls):
        if not url.startswith("http"):
            continue
        links.append(
            {
                "title": titles[index] if index < len(titles) else url,
                "url": url,
                "description": descriptions[index] if index < len(descriptions) else "",
                "type": "link",
            }
        )

    cleaned = "\n\n".join(part for part in parts if part).strip()
    if cleaned:
        return cleaned, links
    return text, links


def _clean_case_answer(answer: str) -> tuple[str, list[dict]]:
    embedded = _extract_embedded_case(answer)
    if not embedded:
        return _clean_jsonish_answer(answer)
    cleaned = _answer_from_structured_payload(embedded)
    links = _normalize_links(embedded.get("links") or [])
    if not links:
        links = _normalize_links(embedded.get("topics_found") or [])
    return cleaned or str(answer or "").strip(), links


def _is_placeholder_case(row: dict) -> bool:
    text = " ".join(
        [
            str(row.get("symptom_title") or ""),
            str(row.get("symptom_description") or ""),
            str(row.get("confirmed_cause") or ""),
            str(row.get("recommended_action") or ""),
            str(row.get("full_answer") or ""),
        ]
    ).lower()
    placeholder_phrases = (
        "диагностика не найдена",
        "нет данных",
        "я готов помочь, но мне не хватает информации",
        "мне не хватает информации",
        "не вижу описания проблемы",
        "не вижу описания симптома",
        "опишите проблему",
        "опишите симптом",
        "please describe",
        "i need more information",
        "i need more info",
        "need more information",
        "diagnosis not found",
        "no data",
    )
    if any(phrase in text for phrase in placeholder_phrases):
        return True
    if not str(row.get("confirmed_cause") or "").strip() and not str(row.get("recommended_action") or "").strip():
        return True
    return False


def _score_case(row: dict, *, active_car: str, symptom: str, language: str, previous_symptom: str = "") -> int:
    recommended_action = str(row.get("recommended_action") or "").strip()
    confirmed_cause = str(row.get("confirmed_cause") or "").strip()
    if _is_placeholder_case(row):
        return 0

    haystack = " ".join(
        [
            str(row.get("symptom_title") or ""),
            str(row.get("symptom_description") or ""),
            confirmed_cause,
            recommended_action,
            str(row.get("full_answer") or ""),
            str(row.get("raw_payload") or ""),
            str(row.get("country") or ""),
        ]
    ).lower()
    if not _vehicle_context_matches(haystack, active_car):
        return 0
    score = 0
    if symptom and _normalize_text(symptom) in _normalize_text(haystack):
        score += 6
    if previous_symptom and _normalize_text(previous_symptom) in _normalize_text(haystack):
        score += 4
    if active_car and _normalize_text(active_car) in _normalize_text(haystack):
        score += 3
    for token in _normalize_text(symptom).split():
        if len(token) > 3 and token in haystack:
            score += 1
        elif any(_token_similar(token, hay_token) for hay_token in _tokenize(haystack)):
            score += 1
    for token in _normalize_text(active_car).split():
        if len(token) > 2 and token in haystack:
            score += 1
    if language and str(row.get("country") or "").lower()[:2] == str(language).lower()[:2]:
        score += 1
    score += int(row.get("success_count") or 0)
    return score


async def find_matching_case(state, decision):
    try:
        client = get_supabase_client()
        rows = [*_knowledge_case_rows(client), *_solved_case_rows(client)]
    except SupabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SupabaseOperationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not rows:
        return None

    rows = [row for row in rows if not _is_placeholder_case(row)]
    if not rows:
        return None

    scored = sorted(
        rows,
        key=lambda row: _score_case(
            row,
            active_car=state.active_car or decision.active_car,
            symptom=state.current_symptom,
            previous_symptom=state.previous_symptom,
            language=state.language,
        ),
        reverse=True,
    )
    row = scored[0]
    best_score = _score_case(
        row,
        active_car=state.active_car or decision.active_car,
        symptom=state.current_symptom,
        previous_symptom=state.previous_symptom,
        language=state.language,
    )
    if best_score < 4:
        return None

    answer = str(row.get("full_answer") or row.get("recommended_action") or row.get("confirmed_cause") or "").strip()
    answer, embedded_links = _clean_case_answer(answer)
    if not answer:
        return None
    links = _row_links(row)
    if embedded_links:
        links = links or embedded_links
    formatted = format_from_kb(
        language=state.language,
        answer=answer,
        links=links,
    )
    return {
        "id": row.get("id"),
        "answer": answer,
        "links": links,
        "formatted_answer": formatted,
        "row": row,
    }


def _parse_history_blocks(history: str) -> list[dict]:
    blocks = [block.strip() for block in str(history or "").split("\n---\n") if block.strip()]
    parsed: list[dict] = []
    for block in blocks:
        fields: dict[str, str] = {}
        links: list[dict] = []
        in_links = False
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.lower() == "links:":
                in_links = True
                continue
            if in_links and line.startswith("- "):
                link_body = line[2:].strip()
                if ": " in link_body:
                    title, url = link_body.split(": ", 1)
                else:
                    title, url = "", link_body
                links.append({"title": title.strip(), "url": url.strip(), "description": "", "type": "link"})
                continue
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key.strip().lower()] = value.strip()
        parsed.append({"fields": fields, "links": links, "raw": block})
    return parsed


async def find_matching_history_case(*, history: str, active_car: str, symptom: str, language: str) -> dict | None:
    blocks = _parse_history_blocks(history)
    if not blocks:
        return None

    symptom_norm = _normalize_text(symptom)
    active_norm = _normalize_text(active_car)
    best: dict | None = None
    best_score = 0

    for block in reversed(blocks):
        fields = block["fields"]
        text_parts = " ".join(
            [
                fields.get("symptom", ""),
                fields.get("user", ""),
                fields.get("assistant", ""),
                fields.get("active_car", ""),
                fields.get("full_answer", ""),
            ]
        )
        haystack = _normalize_text(text_parts)
        if not _vehicle_context_matches(haystack, active_car):
            continue
        score = 0

        if symptom_norm and symptom_norm in haystack:
            score += 6
        for token in _tokenize(symptom):
            if token in haystack:
                score += 2
            elif any(_token_similar(token, hay_token) for hay_token in _tokenize(haystack)):
                score += 1
        if active_norm and active_norm in haystack:
            score += 3
        if fields.get("message_type") in {"parser", "kb_match"}:
            score += 1
        if language and str(fields.get("source") or "").lower()[:2] == str(language).lower()[:2]:
            score += 1

        if score > best_score and (fields.get("assistant") or block["links"]):
            best_score = score
            answer = fields.get("assistant") or ""
            answer, embedded_links = _clean_case_answer(answer)
            links = block["links"] or embedded_links
            best = {
                "id": fields.get("id"),
                "answer": answer,
                "links": links,
                "formatted_answer": format_from_kb(language=language, answer=answer, links=links),
                "row": fields,
                "source_type": "history",
            }

    if best_score < 5:
        return None
    return best


async def save_knowledge_case(normalized, decision, parsed_case) -> dict | None:
    extracted_cases = parsed_case.get("extracted_cases") or []
    first_case = extracted_cases[0] if extracted_cases else {}
    parser_summary = str(parsed_case.get("parser_summary") or "")
    links = _normalize_links(parsed_case.get("links") or [])
    raw_payload = parsed_case.get("_raw") if isinstance(parsed_case.get("_raw"), dict) else parsed_case.get("_raw")
    if not parser_summary.strip() and not extracted_cases:
        return None
    if _is_placeholder_case(
        {
            "symptom_title": decision.active_car or normalized.text or "",
            "symptom_description": normalized.text,
            "confirmed_cause": str(first_case.get("cause") or parser_summary or ""),
            "recommended_action": str(first_case.get("solution") or parser_summary or ""),
            "full_answer": parser_summary,
        }
    ):
        return None
    payload = {
        "symptom_title": (decision.active_car or normalized.text or "")[:500],
        "symptom_description": normalized.text,
        "confirmed_cause": str(first_case.get("cause") or parser_summary or ""),
        "recommended_action": str(first_case.get("solution") or parser_summary or ""),
        "full_answer": parser_summary,
        "raw_payload": raw_payload,
        "forum_links": links,
        "country": normalized.language,
        "source_type": "parser",
        "success_count": 0,
        "confidence": 0.2,
    }
    try:
        created = create_knowledge_case(payload)
    except SupabaseUnavailableError as exc:
        return None
    except SupabaseOperationError as exc:
        return None
    return created


async def save_confirmed_case_to_knowledge(*, diagnostic_request: dict | None, active_car: str = "", language: str = "ru") -> dict | None:
    if not diagnostic_request:
        return None
    vehicle_label = _diagnostic_vehicle_label(diagnostic_request, active_car)
    question = str(
        diagnostic_request.get("raw_question")
        or diagnostic_request.get("question")
        or diagnostic_request.get("symptoms")
        or ""
    ).strip()
    answer = str(diagnostic_request.get("answer") or "").strip()
    if not question or not answer:
        return None
    if _is_placeholder_case(
        {
            "symptom_title": vehicle_label or question,
            "symptom_description": question,
            "confirmed_cause": question,
            "recommended_action": answer,
            "full_answer": answer,
        }
    ):
        return None
    payload = {
        "symptom_title": (vehicle_label or question)[:500],
        "symptom_description": question,
        "confirmed_cause": question,
        "recommended_action": answer[:4000],
        "full_answer": answer,
        "raw_payload": diagnostic_request,
        "forum_links": _normalize_links(diagnostic_request.get("sources") or []),
        "country": language,
        "source_type": "confirmed_feedback",
        "success_count": 1,
        "confidence": 0.7,
    }
    try:
        client = get_supabase_client()
        existing_rows = _knowledge_case_rows(client)
        for row in existing_rows:
            haystack = " ".join(
                [
                    str(row.get("symptom_title") or ""),
                    str(row.get("symptom_description") or ""),
                    str(row.get("confirmed_cause") or ""),
                    str(row.get("recommended_action") or ""),
                    str(row.get("full_answer") or ""),
                ]
            )
            if question and not _contains_any(haystack, question):
                continue
            if vehicle_label and not _vehicle_context_matches(haystack, vehicle_label):
                continue
            updated_payload = {
                "recommended_action": answer[:4000],
                "full_answer": answer,
                "forum_links": payload["forum_links"],
                "raw_payload": diagnostic_request,
                "success_count": int(row.get("success_count") or 0) + 1,
                "confidence": min(float(row.get("confidence") or 0.7) + 0.05, 1.0),
            }
            updated = (
                client.table("knowledge_cases")
                .update(updated_payload)
                .eq("id", row.get("id"))
                .execute()
            )
            updated_rows = getattr(updated, "data", []) or []
            if updated_rows:
                updated_rows[0]["source_table"] = "knowledge_cases"
                _log_confirmed_knowledge_event(
                    diagnostic_request=diagnostic_request,
                    vehicle_label=vehicle_label,
                    answer=answer,
                    language=language,
                    result="knowledge_case_updated_from_feedback",
                )
                return updated_rows[0]
        created = create_knowledge_case(payload)
        if created:
            _log_confirmed_knowledge_event(
                diagnostic_request=diagnostic_request,
                vehicle_label=vehicle_label,
                answer=answer,
                language=language,
                result="knowledge_case_created_from_feedback",
            )
        return created
    except (SupabaseUnavailableError, SupabaseOperationError):
        return None


async def increment_case_success(case_id: int | None, *, source_table: str = "knowledge_cases") -> None:
    if not case_id or source_table != "knowledge_cases":
        return
    try:
        client = get_supabase_client()
        current = client.table("knowledge_cases").select("success_count,confidence").eq("id", case_id).limit(1).execute()
        rows = getattr(current, "data", []) or []
        if not rows:
            return
        row = rows[0]
        success_count = int(row.get("success_count") or 0) + 1
        confidence = min(float(row.get("confidence") or 0) + 0.05, 1.0)
        client.table("knowledge_cases").update({"success_count": success_count, "confidence": confidence}).eq("id", case_id).execute()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Failed to update case success: {exc}") from exc


async def find_latest_case_for_feedback(state) -> dict | None:
    try:
        client = get_supabase_client()
        rows = [*_knowledge_case_rows(client), *_solved_case_rows(client)]
    except SupabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SupabaseOperationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not rows:
        return None

    active_car = str(getattr(state, "active_car", "") or "").strip()
    symptom = str(getattr(state, "previous_symptom", "") or getattr(state, "current_symptom", "") or "").strip()

    ordered_rows = sorted(
        rows,
        key=lambda row: (
            1 if row.get("source_table") == "knowledge_cases" else 0,
            int(row.get("success_count") or 0),
            float(row.get("confidence") or 0),
            int(row.get("id") or 0),
        ),
        reverse=True,
    )

    for row in ordered_rows:
        haystack = " ".join(
            [
                str(row.get("symptom_title") or ""),
                str(row.get("symptom_description") or ""),
                str(row.get("confirmed_cause") or ""),
                str(row.get("recommended_action") or ""),
                str(row.get("full_answer") or ""),
            ]
        )
        if symptom and not _contains_any(haystack, symptom):
            continue
        if active_car and not _contains_any(haystack, active_car):
            continue
        return row

    return None
