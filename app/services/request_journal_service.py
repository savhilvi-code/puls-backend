from __future__ import annotations

from datetime import datetime, timezone
import re

from fastapi import HTTPException

from app.database.supabase import SupabaseOperationError, SupabaseUnavailableError, get_supabase_client
from app.services.formatter_service import _clean_text
from app.services.kb_service import _clean_case_answer


def _rows(response) -> list[dict]:
    return getattr(response, "data", []) or []


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


def _sort_timestamp(value: str | None) -> float:
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except Exception:
        return 0.0


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
            label = " ".join(words[index:index + 8]).strip()
            year = re.search(r"\b(19[8-9]\d|20[0-3]\d)\b", normalized)
            engine = re.search(r"\b(1g[- ]?gze|sr20vet|qr20|qr25|2gr|1gr|ej20|ej25|k20|k24|m57|n52|n54|n55|b58)\b", normalized, re.IGNORECASE)
            if year and year.group(0) not in label:
                label = f"{label} {year.group(0)}"
            if engine and engine.group(0).lower() not in label.lower():
                label = f"{label} {engine.group(0)}"
            return label
    return ""


def _vehicle_label(row: dict | None) -> str:
    row = row or {}
    return " ".join(
        str(row.get(key) or "").strip()
        for key in ("brand", "model", "year", "engine")
        if str(row.get(key) or "").strip()
    )


def _load_vehicle_labels(client, conversation_rows: list[dict], diagnostic_rows: list[dict]) -> dict[int, str]:
    ids = sorted(
        {
            int(row.get("vehicle_id"))
            for row in [*conversation_rows, *diagnostic_rows]
            if row.get("vehicle_id")
        }
    )
    if not ids:
        return {}
    try:
        response = client.table("vehicles").select("id,brand,model,year,engine").in_("id", ids).execute()
        return {
            int(row["id"]): _vehicle_label(row)
            for row in _rows(response)
            if row.get("id") and _vehicle_label(row)
        }
    except Exception:
        return {}


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
            user_rows = _rows(client.table("users").select("id,email").eq("email", email).limit(1).execute())
            if user_rows:
                resolved_user_id = user_rows[0].get("id")
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Failed to resolve user history owner: {exc}") from exc

    if resolved_user_id is None:
        return []

    try:
        conversation_rows = _rows(
            client.table("conversations")
            .select("id,user_id,vehicle_id,title,status,created_at,updated_at,last_message_at")
            .eq("user_id", resolved_user_id)
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
        )
        if not conversation_rows:
            return []
        conversation_ids = [int(row["id"]) for row in conversation_rows if row.get("id")]
        message_rows = _rows(
            client.table("messages")
            .select("id,conversation_id,vehicle_id,role,message_text,language,created_at")
            .in_("conversation_id", conversation_ids)
            .order("created_at", desc=False)
            .execute()
        )
        diagnostic_rows = _rows(
            client.table("diagnostic_requests")
            .select("id,conversation_id,vehicle_id,question,answer,status,request_type,parser_used,deep_search_used,sources,videos,created_at")
            .in_("conversation_id", conversation_ids)
            .order("created_at", desc=True)
            .execute()
        )
    except SupabaseOperationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Failed to load request history: {exc}") from exc

    vehicle_labels = _load_vehicle_labels(client, conversation_rows, diagnostic_rows)
    messages_by_conversation: dict[int, list[dict]] = {}
    for row in message_rows:
        cid = int(row.get("conversation_id") or 0)
        messages_by_conversation.setdefault(cid, []).append(row)

    conversation_by_id: dict[int, dict] = {}
    diagnostic_by_conversation: dict[int, list[dict]] = {}
    for row in diagnostic_rows:
        cid = int(row.get("conversation_id") or 0)
        diagnostic_by_conversation.setdefault(cid, []).append(row)

    items: list[dict] = []
    for row in conversation_rows:
        cid = int(row.get("id") or 0)
        conversation_by_id[cid] = row
        conversation_messages = messages_by_conversation.get(cid, [])
        user_messages = [item for item in conversation_messages if str(item.get("role") or "") == "user"]
        assistant_messages = [item for item in conversation_messages if str(item.get("role") or "") == "assistant"]
        first_user = str((user_messages[0] if user_messages else {}).get("message_text") or row.get("title") or "").strip()
        last_assistant = str((assistant_messages[-1] if assistant_messages else {}).get("message_text") or "").strip()
        request_rows = diagnostic_by_conversation.get(cid, [])
        if request_rows:
            continue

        answer_text, embedded_links = _clean_case_answer(str(last_assistant or ""))
        answer_text = _clean_text(answer_text, max_len=2600)
        vehicle_label = (
            vehicle_labels.get(int(row.get("vehicle_id") or 0), "")
            or _extract_vehicle_label(first_user)
        )
        items.append(
            {
                "id": cid,
                "conversation_id": cid,
                "question": first_user,
                "answer": answer_text,
                "date": _format_created_at(row.get("updated_at") or row.get("last_message_at") or row.get("created_at")),
                "status": str(row.get("status") or ""),
                "vehicle": vehicle_label,
                "vehicle_id": row.get("vehicle_id"),
                "type": "conversation",
                "source": "web",
                "sources": embedded_links or [],
                "videos": [],
                "parser_used": False,
                "deep_search_used": False,
                "created_at": row.get("updated_at") or row.get("last_message_at") or row.get("created_at") or "",
                "message_count": len(conversation_messages),
            }
        )

    for request in diagnostic_rows:
        cid = int(request.get("conversation_id") or 0)
        conversation_row = conversation_by_id.get(cid, {})
        question_text = str(request.get("question") or "").strip()
        answer_text, embedded_links = _clean_case_answer(str(request.get("answer") or ""))
        answer_text = _clean_text(answer_text, max_len=2600)
        vehicle_label = (
            vehicle_labels.get(int(request.get("vehicle_id") or 0), "")
            or vehicle_labels.get(int(conversation_row.get("vehicle_id") or 0), "")
            or _extract_vehicle_label(question_text)
        )
        items.append(
            {
                "id": request.get("id"),
                "conversation_id": cid,
                "question": question_text,
                "answer": answer_text,
                "date": _format_created_at(request.get("created_at") or conversation_row.get("updated_at") or conversation_row.get("created_at")),
                "status": str(request.get("status") or conversation_row.get("status") or ""),
                "vehicle": vehicle_label,
                "vehicle_id": request.get("vehicle_id") or conversation_row.get("vehicle_id"),
                "type": str(request.get("request_type") or "conversation"),
                "source": "web",
                "sources": request.get("sources") or embedded_links or [],
                "videos": request.get("videos") or [],
                "parser_used": bool(request.get("parser_used")),
                "deep_search_used": bool(request.get("deep_search_used")),
                "created_at": request.get("created_at") or "",
                "message_count": len(messages_by_conversation.get(cid, [])),
            }
        )

    items.sort(key=lambda item: _sort_timestamp(item.get("created_at")), reverse=True)
    return items[:limit]


async def get_conversation_messages(*, conversation_id: int, user_id: int | None = None, email: str = "") -> list[dict]:
    try:
        client = get_supabase_client()
    except SupabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    resolved_user_id = user_id
    if resolved_user_id is None and email:
        user_rows = _rows(client.table("users").select("id,email").eq("email", email).limit(1).execute())
        if user_rows:
            resolved_user_id = user_rows[0].get("id")
    if resolved_user_id is None:
        return []

    conversation_rows = _rows(
        client.table("conversations")
        .select("id,user_id,vehicle_id")
        .eq("id", conversation_id)
        .eq("user_id", resolved_user_id)
        .limit(1)
        .execute()
    )
    if not conversation_rows:
        return []

    message_rows = _rows(
        client.table("messages")
        .select("id,conversation_id,vehicle_id,role,message_text,language,created_at")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=False)
        .execute()
    )
    vehicle_labels = _load_vehicle_labels(client, conversation_rows, message_rows)
    return [
        {
            "id": row.get("id"),
            "conversation_id": row.get("conversation_id"),
            "vehicle_id": row.get("vehicle_id"),
            "vehicle": vehicle_labels.get(int(row.get("vehicle_id") or 0), ""),
            "role": row.get("role") or "",
            "text": row.get("message_text") or "",
            "language": row.get("language") or "ru",
            "date": _format_created_at(row.get("created_at")),
            "created_at": row.get("created_at") or "",
        }
        for row in message_rows
    ]
