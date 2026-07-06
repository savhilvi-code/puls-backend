from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.database.supabase import get_supabase_client


def _rows(response) -> list[dict]:
    return getattr(response, "data", []) or []


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _vehicle_snapshot_from_text(text: str) -> dict[str, Any]:
    raw = " ".join(str(text or "").split())
    year_match = re.search(r"\b(19[8-9]\d|20[0-3]\d)\b", raw)
    engine_match = re.search(
        r"\b(1g[- ]?gze|1ggze|sr20vet|qr20|qr25|2gr|1gr|1zz|2zz|ej20|ej25|k20|k24|m57|n52|n54|n55|b58)\b",
        raw,
        re.IGNORECASE,
    )
    brand_match = re.search(
        r"\b(toyota|nissan|honda|mazda|subaru|mitsubishi|lexus|infiniti|bmw|mercedes(?:-benz)?|audi|volkswagen|ford|hyundai|kia)\b",
        raw,
        re.IGNORECASE,
    )
    words = raw.split()
    brand = ""
    model = ""
    if brand_match:
        brand = brand_match.group(0)
        lowered_words = [word.lower() for word in words]
        try:
            brand_index = lowered_words.index(brand.lower())
        except ValueError:
            brand_index = -1
        if brand_index >= 0 and brand_index + 1 < len(words):
            model = words[brand_index + 1]
    return {
        "brand": brand or (words[0] if words else ""),
        "model": model or (words[1] if len(words) > 1 else ""),
        "year": int(year_match.group(0)) if year_match else None,
        "engine": engine_match.group(0) if engine_match else "",
    }


def _load_vehicle_snapshot(vehicle_id: int | None) -> dict[str, Any]:
    if not vehicle_id:
        return {}
    response = (
        get_supabase_client()
        .table("vehicles")
        .select("brand,model,year,engine")
        .eq("id", vehicle_id)
        .limit(1)
        .execute()
    )
    rows = _rows(response)
    if not rows:
        return {}
    row = rows[0]
    return {
        "brand": row.get("brand") or "",
        "model": row.get("model") or "",
        "year": row.get("year") or None,
        "engine": row.get("engine") or "",
    }


def create_diagnostic_request(
    *,
    user_id: int | None,
    conversation_id: int | None,
    vehicle_id: int | None,
    question: str,
    answer: str,
    language: str,
    request_type: str,
    status: str,
    parser_used: bool,
    deep_search_used: bool,
    request_cost_counted: bool,
    sources: list[dict] | None,
    videos: list[dict] | None,
) -> dict | None:
    if user_id is None or not str(question or "").strip():
        return None
    snapshot = _load_vehicle_snapshot(vehicle_id) or _vehicle_snapshot_from_text(question)
    payload = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "vehicle_id": vehicle_id,
        "question": str(question or "").strip(),
        "raw_question": str(question or "").strip(),
        "symptoms": str(question or "").strip(),
        "answer": str(answer or "").strip(),
        "language": language or "ru",
        "request_type": request_type,
        "status": status,
        "parser_used": parser_used,
        "deep_search_used": deep_search_used,
        "request_cost_counted": request_cost_counted,
        "sources": sources or [],
        "videos": videos or [],
        "brand": snapshot.get("brand") or None,
        "model": snapshot.get("model") or None,
        "year": snapshot.get("year") or None,
        "engine": snapshot.get("engine") or None,
        "updated_at": _now_iso(),
    }
    response = get_supabase_client().table("diagnostic_requests").insert(payload).execute()
    rows = _rows(response)
    return rows[0] if rows else None


def update_diagnostic_request(*, diagnostic_request_id: int | None, payload: dict[str, Any]) -> dict | None:
    if not diagnostic_request_id:
        return None
    data = {**payload, "updated_at": _now_iso()}
    response = (
        get_supabase_client()
        .table("diagnostic_requests")
        .update(data)
        .eq("id", diagnostic_request_id)
        .execute()
    )
    rows = _rows(response)
    return rows[0] if rows else None


def get_latest_diagnostic_request(*, user_id: int | None, conversation_id: int | None = None) -> dict | None:
    if user_id is None:
        return None
    query = (
        get_supabase_client()
        .table("diagnostic_requests")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(20)
    )
    if conversation_id:
        query = query.eq("conversation_id", conversation_id)
    rows = _rows(query.execute())
    return rows[0] if rows else None
