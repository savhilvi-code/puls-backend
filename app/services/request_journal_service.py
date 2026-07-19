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


def _normalized_match_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _match_request_for_pair(
    *,
    request_rows: list[dict],
    used_request_ids: set[int],
    question_text: str,
    answer_text: str,
) -> dict | None:
    normalized_question = _normalized_match_text(question_text)
    normalized_answer = _normalized_match_text(answer_text)
    if not normalized_question and not normalized_answer:
        return None

    for request in request_rows:
        request_id = int(request.get("id") or 0)
        if request_id and request_id in used_request_ids:
            continue
        request_question = _normalized_match_text(request.get("question"))
        request_answer = _normalized_match_text(request.get("answer"))
        if normalized_question and request_question and (
            normalized_question == request_question
            or normalized_question in request_question
            or request_question in normalized_question
        ):
            if request_id:
                used_request_ids.add(request_id)
            return request
        if normalized_answer and request_answer and (
            normalized_answer == request_answer
            or normalized_answer in request_answer
            or request_answer in normalized_answer
        ):
            if request_id:
                used_request_ids.add(request_id)
            return request
    return None


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

    conversation_by_id = {
        int(row.get("id") or 0): row
        for row in conversation_rows
        if row.get("id")
    }
    diagnostic_by_conversation: dict[int, list[dict]] = {}
    for row in diagnostic_rows:
        cid = int(row.get("conversation_id") or 0)
        diagnostic_by_conversation.setdefault(cid, []).append(row)

    items: list[dict] = []
    for cid, conversation_row in conversation_by_id.items():
        conversation_messages = messages_by_conversation.get(cid, [])
        request_rows = diagnostic_by_conversation.get(cid, [])
        used_request_ids: set[int] = set()
        pending_user: dict | None = None
        conversation_item_count = 0

        for message in conversation_messages:
            role = str(message.get("role") or "").strip().lower()
            text = str(message.get("message_text") or "").strip()
            if role == "user" and text:
                pending_user = message
                continue
            if role != "assistant" or not text or pending_user is None:
                continue

            question_text = str(pending_user.get("message_text") or "").strip()
            answer_text, embedded_links = _clean_case_answer(text)
            answer_text = _clean_text(answer_text, max_len=2600)
            matched_request = _match_request_for_pair(
                request_rows=request_rows,
                used_request_ids=used_request_ids,
                question_text=question_text,
                answer_text=answer_text,
            )

            vehicle_label = (
                vehicle_labels.get(int(message.get("vehicle_id") or 0), "")
                or vehicle_labels.get(int(pending_user.get("vehicle_id") or 0), "")
                or vehicle_labels.get(int((matched_request or {}).get("vehicle_id") or 0), "")
                or vehicle_labels.get(int(conversation_row.get("vehicle_id") or 0), "")
                or _extract_vehicle_label(question_text)
            )
            item_created_at = (
                message.get("created_at")
                or pending_user.get("created_at")
                or (matched_request or {}).get("created_at")
                or conversation_row.get("updated_at")
                or conversation_row.get("created_at")
                or ""
            )
            items.append(
                {
                    "id": (matched_request or {}).get("id") or message.get("id") or pending_user.get("id") or f"{cid}-{len(items)}",
                    "conversation_id": cid,
                    "question": question_text,
                    "answer": answer_text,
                    "date": _format_created_at(item_created_at),
                    "status": str((matched_request or {}).get("status") or conversation_row.get("status") or ""),
                    "vehicle": vehicle_label,
                    "vehicle_id": (
                        message.get("vehicle_id")
                        or pending_user.get("vehicle_id")
                        or (matched_request or {}).get("vehicle_id")
                        or conversation_row.get("vehicle_id")
                    ),
                    "type": str((matched_request or {}).get("request_type") or "conversation"),
                    "source": "web",
                    "sources": (matched_request or {}).get("sources") or embedded_links or [],
                    "videos": (matched_request or {}).get("videos") or [],
                    "parser_used": bool((matched_request or {}).get("parser_used")),
                    "deep_search_used": bool((matched_request or {}).get("deep_search_used")),
                    "created_at": item_created_at,
                    "message_count": len(conversation_messages),
                }
            )
            conversation_item_count += 1
            pending_user = None

        if conversation_item_count or not conversation_messages:
            continue

        title_text = str(conversation_row.get("title") or "").strip()
        if not title_text:
            continue
        items.append(
            {
                "id": cid,
                "conversation_id": cid,
                "question": title_text,
                "answer": "",
                "date": _format_created_at(conversation_row.get("updated_at") or conversation_row.get("last_message_at") or conversation_row.get("created_at")),
                "status": str(conversation_row.get("status") or ""),
                "vehicle": vehicle_labels.get(int(conversation_row.get("vehicle_id") or 0), "") or _extract_vehicle_label(title_text),
                "vehicle_id": conversation_row.get("vehicle_id"),
                "type": "conversation",
                "source": "web",
                "sources": [],
                "videos": [],
                "parser_used": False,
                "deep_search_used": False,
                "created_at": conversation_row.get("updated_at") or conversation_row.get("last_message_at") or conversation_row.get("created_at") or "",
                "message_count": len(conversation_messages),
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
