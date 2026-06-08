from fastapi import HTTPException

from app.database.supabase import (
    SupabaseOperationError,
    SupabaseUnavailableError,
    create_knowledge_case,
    get_supabase_client,
)
from app.services.formatter_service import format_from_kb


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def _contains_any(haystack: str, needle: str) -> bool:
    hay = _normalize_text(haystack)
    need = _normalize_text(needle)
    return bool(need) and need in hay


def _score_case(row: dict, *, active_car: str, symptom: str, language: str, previous_symptom: str = "") -> int:
    recommended_action = str(row.get("recommended_action") or "").strip()
    confirmed_cause = str(row.get("confirmed_cause") or "").strip()
    if not recommended_action and not confirmed_cause:
        return 0

    haystack = " ".join(
        [
            str(row.get("symptom_title") or ""),
            str(row.get("symptom_description") or ""),
            confirmed_cause,
            recommended_action,
            str(row.get("country") or ""),
        ]
    ).lower()
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
        response = client.table("knowledge_cases").select(
            "id,symptom_title,symptom_description,confirmed_cause,recommended_action,country,source_type,success_count,confidence"
        ).order("success_count", desc=True).limit(100).execute()
        rows = getattr(response, "data", []) or []
    except SupabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SupabaseOperationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

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

    answer = str(row.get("recommended_action") or row.get("confirmed_cause") or "").strip()
    if not answer:
        return None
    formatted = format_from_kb(
        language=state.language,
        answer=answer,
        links=[],
    )
    return {
        "id": row.get("id"),
        "answer": answer,
        "links": [],
        "formatted_answer": formatted,
        "row": row,
    }


async def save_knowledge_case(normalized, decision, parsed_case) -> dict | None:
    extracted_cases = parsed_case.get("extracted_cases") or []
    first_case = extracted_cases[0] if extracted_cases else {}
    parser_summary = str(parsed_case.get("parser_summary") or "")
    payload = {
        "symptom_title": (decision.active_car or normalized.text or "")[:500],
        "symptom_description": normalized.text,
        "confirmed_cause": str(first_case.get("cause") or parser_summary or ""),
        "recommended_action": str(first_case.get("solution") or parser_summary or ""),
        "country": normalized.language,
        "source_type": "parser",
        "success_count": 0,
        "confidence": 0.2,
    }
    try:
        created = create_knowledge_case(payload)
    except SupabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SupabaseOperationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return created


async def increment_case_success(case_id: int | None) -> None:
    if not case_id:
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
        response = client.table("knowledge_cases").select(
            "id,symptom_title,symptom_description,confirmed_cause,recommended_action,country,source_type,success_count,confidence"
        ).order("id", desc=True).limit(200).execute()
        rows = getattr(response, "data", []) or []
    except SupabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SupabaseOperationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not rows:
        return None

    active_car = str(getattr(state, "active_car", "") or "").strip()
    symptom = str(getattr(state, "previous_symptom", "") or getattr(state, "current_symptom", "") or "").strip()

    for row in rows:
        haystack = " ".join(
            [
                str(row.get("symptom_title") or ""),
                str(row.get("symptom_description") or ""),
                str(row.get("confirmed_cause") or ""),
                str(row.get("recommended_action") or ""),
            ]
        )
        if symptom and not _contains_any(haystack, symptom):
            continue
        if active_car and not _contains_any(haystack, active_car):
            continue
        return row

    return None
