from __future__ import annotations

from fastapi import HTTPException

from app.database.supabase import SupabaseOperationError, SupabaseUnavailableError, get_supabase_client
from app.services.formatter_service import _clean_text
from app.services.kb_service import _clean_case_answer
from datetime import datetime, timezone
import re


def _format_created_at(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone().strftime("%d.%m.%Y, %H:%M")
    except Exception:
        return raw


def _derive_status(message_type: str) -> str:
    message_type = str(message_type or "").strip().lower()
    if message_type in {"greeting", "limit"}:
        return message_type
    if message_type in {"feedback_helped", "resolved"}:
        return "resolved"
    if message_type in {"feedback_not_helped", "followup_deep"}:
        return "followup"
    if message_type in {"clarification", "new_diagnostic", "parser", "kb_match", "followup"}:
        return "open"
    return "open"


def _extract_vehicle_label(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    normalized = re.sub(r"[.,;!?()]+", " ", raw)
    lowered = normalized.lower()
    brands = (
        "toyota",
        "nissan",
        "honda",
        "mazda",
        "subaru",
        "mitsubishi",
        "lexus",
        "infiniti",
        "bmw",
        "mercedes",
        "audi",
        "volkswagen",
        "peugeot",
        "renault",
        "ford",
        "hyundai",
        "kia",
    )
    found = next((brand for brand in brands if brand in lowered), "")
    if not found:
        return ""
    words = normalized.split()
    for index in range(len(words)):
        if words[index].lower() == found:
            label = " ".join(words[index:index + 7]).strip()
            year = re.search(r"\b(19[8-9]\d|20[0-3]\d)\b", normalized)
            engine = re.search(r"\b(1g[- ]?gze|sr20vet|qr20|qr25|2gr|1gr|ej20|ej25|k20|k24|m57|n52|n54|n55|b58)\b", normalized, re.IGNORECASE)
            if year and year.group(0) not in label:
                label = f"{label} {year.group(0)}"
            if engine and engine.group(0).lower() not in label.lower():
                label = f"{label} {engine.group(0)}"
            return label
    return ""


def _vehicle_label(row: dict | None) -> str:
    if not row:
        return ""
    return " ".join(
        str(row.get(key) or "").strip()
        for key in ("brand", "model", "year", "engine")
        if str(row.get(key) or "").strip()
    )


def _load_vehicle_labels(client, rows: list[dict]) -> dict[int, str]:
    ids = sorted({int(row.get("vehicle_id")) for row in rows if row.get("vehicle_id")})
    if not ids:
        return {}
    try:
        response = client.table("vehicles").select("id,brand,model,year,engine").in_("id", ids).execute()
        return {
            int(row["id"]): _vehicle_label(row)
            for row in (getattr(response, "data", []) or [])
            if row.get("id") and _vehicle_label(row)
        }
    except Exception:
        return {}


async def save_diagnostic_request(*, user_id: int | None, normalized, answer: str, message_type: str, vehicle_id: int | None = None, vehicle_profile_id: int | None = None) -> dict | None:
    if user_id is None:
        return None

    status = _derive_status(message_type)
    if status == "greeting":
        return None

    payload = {
        "user_id": user_id,
        "vehicle_id": vehicle_id,
        "vehicle_profile_id": vehicle_profile_id,
        "question": str(normalized.text or "").strip(),
        "answer": str(answer or "").strip(),
        "language": str(normalized.language or "ru"),
        "request_type": "text",
        "status": status,
        "source": str(normalized.source or "web"),
    }

    try:
        client = get_supabase_client()
        response = client.table("diagnostic_requests").insert(payload).execute()
        rows = getattr(response, "data", []) or []
        return rows[0] if rows else None
    except SupabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SupabaseOperationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Failed to save diagnostic request: {exc}") from exc


async def get_user_request_history(*, user_id: int | None = None, email: str = "", limit: int = 50) -> list[dict]:
    if limit <= 0:
        limit = 50

    try:
        client = get_supabase_client()
    except SupabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    resolved_user_id = user_id
    if resolved_user_id is None and email:
        try:
            user_response = client.table("users").select("id,car_info,email").eq("email", email).limit(1).execute()
            user_rows = getattr(user_response, "data", []) or []
            if user_rows:
                resolved_user_id = user_rows[0].get("id")
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Failed to resolve user history owner: {exc}") from exc

    if resolved_user_id is None:
        return []

    try:
        response = (
            client.table("diagnostic_requests")
            .select("id,user_id,vehicle_id,vehicle_profile_id,question,answer,language,request_type,status,source,created_at,parser_used,deep_search_used,sources,videos")
            .eq("user_id", resolved_user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = getattr(response, "data", []) or []
    except SupabaseOperationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Failed to load diagnostic history: {exc}") from exc

    vehicle_labels = _load_vehicle_labels(client, rows)
    items: list[dict] = []
    for row in rows:
        question = row.get("question") or ""
        answer, embedded_links = _clean_case_answer(row.get("answer") or "")
        answer = _clean_text(answer, max_len=2600)
        sources = row.get("sources") or embedded_links or []
        items.append(
            {
                "id": row.get("id"),
                "question": question,
                "answer": answer,
                "date": _format_created_at(row.get("created_at")),
                "status": row.get("status") or "",
                "vehicle": vehicle_labels.get(int(row.get("vehicle_id") or 0), "") or _extract_vehicle_label(question),
                "vehicle_id": row.get("vehicle_id"),
                "type": row.get("request_type") or "text",
                "source": row.get("source") or "web",
                "sources": sources,
                "videos": row.get("videos") or [],
                "parser_used": bool(row.get("parser_used")),
                "deep_search_used": bool(row.get("deep_search_used")),
                "created_at": row.get("created_at") or "",
            }
        )

    return items
