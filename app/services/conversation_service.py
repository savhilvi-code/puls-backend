from __future__ import annotations

import re
from datetime import datetime, timezone

from app.database.supabase import get_supabase_client


def _rows(response) -> list[dict]:
    return getattr(response, "data", []) or []


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_vehicle_label(text: str) -> str:
    raw = " ".join(str(text or "").split())
    if not raw:
        return ""
    match = re.search(
        r"\b(toyota|nissan|honda|mazda|subaru|mitsubishi|lexus|infiniti|bmw|mercedes|audi|volkswagen|ford|hyundai|kia)\b.{0,40}",
        raw,
        re.IGNORECASE,
    )
    return match.group(0).strip() if match else ""


def _normalize_context_text(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _looks_like_service_query(text: str) -> bool:
    lowered = _normalize_context_text(text)
    service_terms = (
        "\u043a\u0430\u043a\u043e\u0435 \u043c\u0430\u0441\u043b\u043e",
        "\u043a\u0430\u043a\u043e\u0435 \u043c\u0430\u0441\u043b\u043e \u043f\u043e\u0434\u0445\u043e\u0434\u0438\u0442",
        "\u043a\u0430\u043a\u043e\u0435 \u043c\u0430\u0441\u043b\u043e \u043b\u0438\u0442\u044c",
        "\u043a\u0430\u043a\u043e\u0435 \u043c\u0430\u0441\u043b\u043e \u0437\u0430\u043b\u0438\u0442\u044c",
        "\u043a\u0430\u043a\u0443\u044e \u0436\u0438\u0434\u043a\u043e\u0441\u0442\u044c",
        "\u043a\u0430\u043a\u043e\u0439 \u0430\u043d\u0442\u0438\u0444\u0440\u0438\u0437",
        "\u043a\u0430\u043a\u043e\u0439 atf",
        "\u0442\u0440\u0430\u043d\u0441\u043c\u0438\u0441\u0441\u0438\u043e\u043d\u043d\u043e\u0435 \u043c\u0430\u0441\u043b\u043e",
        "\u0432\u044f\u0437\u043a\u043e\u0441\u0442\u044c \u043c\u0430\u0441\u043b\u0430",
        "\u0434\u043e\u043f\u0443\u0441\u043a \u043c\u0430\u0441\u043b\u0430",
        "what oil",
        "which oil",
        "oil recommendation",
        "oil viscosity",
        "coolant",
        "antifreeze",
        "transmission fluid",
        "brake fluid",
        "power steering fluid",
    )
    if any(term in lowered for term in service_terms):
        return True

    mentions_fluid_topic = any(
        token in lowered
        for token in ("\u043c\u0430\u0441\u043b\u043e", "\u0436\u0438\u0434\u043a", "\u0430\u043d\u0442\u0438\u0444\u0440\u0438\u0437", "oil", "coolant", "atf", "fluid")
    )
    asks_for_selection = any(
        token in lowered
        for token in (
            "\u043a\u0430\u043a\u043e\u0435",
            "\u043a\u0430\u043a\u0443\u044e",
            "\u043a\u0430\u043a\u043e\u0439",
            "\u0437\u0430\u043b\u0438\u0442\u044c",
            "\u043b\u0438\u0442\u044c",
            "\u043f\u043e\u0434\u0445\u043e\u0434\u0438\u0442",
            "\u0432\u044f\u0437\u043a\u043e\u0441\u0442\u044c",
            "\u0434\u043e\u043f\u0443\u0441\u043a",
            "what",
            "which",
            "recommendation",
            "viscosity",
            "spec",
        )
    )
    return mentions_fluid_topic and asks_for_selection


def _vehicle_label(row: dict | None) -> str:
    row = row or {}
    parts = [row.get("brand"), row.get("model"), row.get("year"), row.get("engine")]
    return " ".join(str(part).strip() for part in parts if str(part or "").strip()).strip()


def _load_vehicle_labels(vehicle_ids: list[int]) -> dict[int, str]:
    if not vehicle_ids:
        return {}
    response = (
        get_supabase_client()
        .table("vehicles")
        .select("id,brand,model,year,engine")
        .in_("id", sorted(set(vehicle_ids)))
        .execute()
    )
    return {
        int(row["id"]): _vehicle_label(row)
        for row in _rows(response)
        if row.get("id")
    }


def get_or_create_conversation(
    *,
    user_id: int | None,
    vehicle_id: int | None,
    title: str,
    force_new_context: bool = False,
) -> dict | None:
    if user_id is None:
        return None
    client = get_supabase_client()
    rows = _rows(
        client.table("conversations")
        .select("*")
        .eq("user_id", user_id)
        .eq("status", "active")
        .order("updated_at", desc=True)
        .limit(10)
        .execute()
    )

    chosen = None
    if not force_new_context:
        if vehicle_id is not None:
            chosen = next((row for row in rows if row.get("vehicle_id") == vehicle_id), None)
        else:
            chosen = next((row for row in rows if not row.get("vehicle_id")), None)
        if chosen is None and rows:
            chosen = rows[0]

    if chosen:
        updates = {"last_message_at": _now_iso(), "updated_at": _now_iso()}
        if title and not str(chosen.get("title") or "").strip():
            updates["title"] = title[:160]
        if vehicle_id != chosen.get("vehicle_id"):
            updates["vehicle_id"] = vehicle_id
        response = client.table("conversations").update(updates).eq("id", chosen["id"]).execute()
        updated_rows = _rows(response)
        return updated_rows[0] if updated_rows else {**chosen, **updates}

    payload = {
        "user_id": user_id,
        "vehicle_id": vehicle_id,
        "channel": "site",
        "status": "active",
        "title": title[:160] if title else "",
        "last_message_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    response = client.table("conversations").insert(payload).execute()
    created_rows = _rows(response)
    return created_rows[0] if created_rows else None


def save_message(
    *,
    conversation_id: int | None,
    user_id: int | None,
    vehicle_id: int | None,
    role: str,
    text: str,
    language: str,
) -> dict | None:
    if conversation_id is None or user_id is None or not str(text or "").strip():
        return None
    response = get_supabase_client().table("messages").insert(
        {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "vehicle_id": vehicle_id,
            "role": role,
            "message_text": str(text or "").strip(),
            "language": language or "ru",
        }
    ).execute()
    rows = _rows(response)
    return rows[0] if rows else None


def get_latest_conversation_context(*, user_id: int | None) -> dict[str, str]:
    if user_id is None:
        return {}

    client = get_supabase_client()
    conversation_rows = _rows(
        client.table("conversations")
        .select("id,vehicle_id,updated_at")
        .eq("user_id", user_id)
        .eq("status", "active")
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    if not conversation_rows:
        return {}

    conversation = conversation_rows[0]
    conversation_id = conversation.get("id")
    if not conversation_id:
        return {}

    message_rows = _rows(
        client.table("messages")
        .select("role,message_text,created_at")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=True)
        .limit(12)
        .execute()
    )
    if not message_rows:
        return {}

    message_rows.reverse()

    last_assistant_text = ""
    last_user_text = ""
    latest_service_query = ""
    for index in range(len(message_rows) - 1, -1, -1):
        row = message_rows[index]
        role = str(row.get("role") or "").strip().lower()
        text = str(row.get("message_text") or "").strip()
        if role == "assistant" and text:
            last_assistant_text = text
            for previous_index in range(index - 1, -1, -1):
                previous_row = message_rows[previous_index]
                if str(previous_row.get("role") or "").strip().lower() == "user":
                    last_user_text = str(previous_row.get("message_text") or "").strip()
                    break
            break

    for row in reversed(message_rows):
        if str(row.get("role") or "").strip().lower() != "user":
            continue
        text = str(row.get("message_text") or "").strip()
        if text and _looks_like_service_query(text):
            latest_service_query = text
            break

    vehicle_label = ""
    vehicle_id = conversation.get("vehicle_id")
    if vehicle_id:
        vehicle_label = _load_vehicle_labels([int(vehicle_id)]).get(int(vehicle_id), "")

    return {
        "conversation_id": str(conversation_id),
        "active_car": vehicle_label,
        "last_user_text": last_user_text,
        "last_assistant_text": last_assistant_text,
        "latest_service_query": latest_service_query,
    }


def build_user_conversation_history(*, user_id: int | None, limit: int = 12) -> str:
    if user_id is None:
        return ""
    client = get_supabase_client()
    response = (
        client.table("diagnostic_requests")
        .select("id,vehicle_id,question,answer,status,request_type,created_at,sources")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = list(reversed(_rows(response)))
    if not rows:
        return ""
    vehicle_labels = _load_vehicle_labels([int(row["vehicle_id"]) for row in rows if row.get("vehicle_id")])
    blocks: list[str] = []
    for row in rows:
        question = str(row.get("question") or "").strip()
        answer = str(row.get("answer") or "").strip()
        active_car = (
            vehicle_labels.get(int(row.get("vehicle_id") or 0), "")
            or _extract_vehicle_label(question)
        )
        links = row.get("sources") or []
        message_type = "parser"
        if str(row.get("request_type") or "") == "kb":
            message_type = "kb_match"
        elif str(row.get("request_type") or "") == "deep_search":
            message_type = "followup_deep"
        block = [
            "source: web",
            f"message_type: {message_type}",
            f"active_car: {active_car}",
            f"symptom: {question}",
            f"user: {question}",
            f"assistant: {answer}",
        ]
        if isinstance(links, list) and links:
            block.append("links:")
            for item in links[:8]:
                if isinstance(item, dict) and item.get("url"):
                    block.append(f"- {item.get('title') or item.get('url')}: {item.get('url')}")
        blocks.append("\n".join(block))
    return "\n---\n".join(blocks)


def get_latest_active_car(*, user_id: int | None) -> str:
    if user_id is None:
        return ""
    client = get_supabase_client()
    rows = _rows(
        client.table("diagnostic_requests")
        .select("vehicle_id,question,created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(5)
        .execute()
    )
    if not rows:
        return ""
    vehicle_ids = [int(row["vehicle_id"]) for row in rows if row.get("vehicle_id")]
    labels = _load_vehicle_labels(vehicle_ids)
    for row in rows:
        if row.get("vehicle_id") and labels.get(int(row["vehicle_id"])):
            return labels[int(row["vehicle_id"])]
        label = _extract_vehicle_label(str(row.get("question") or ""))
        if label:
            return label
    return ""
