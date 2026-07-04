from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.database.supabase import SupabaseOperationError, SupabaseUnavailableError, get_supabase_client, is_supabase_configured

VIDEO_DOMAINS = ("youtube.com", "youtu.be", "rutube.ru", "vimeo.com")
logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rows(response) -> list[dict]:
    return getattr(response, "data", []) or []


def _safe_execute(operation, default=None):
    if not is_supabase_configured():
        logger.warning("Supabase operation skipped because Supabase is not configured.")
        return default
    try:
        return operation()
    except (SupabaseUnavailableError, SupabaseOperationError) as exc:
        logger.exception("Supabase operation failed: %s", exc)
        return default
    except Exception as exc:
        logger.exception("Unexpected Supabase operation failure: %s", exc)
        return default


def _normalize_links(links: list[dict] | None) -> list[dict]:
    normalized: list[dict] = []
    seen: set[str] = set()
    for item in links or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("link") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        link_type = str(item.get("type") or "").strip().lower()
        if not link_type:
            link_type = "video" if any(domain in url.lower() for domain in VIDEO_DOMAINS) else "link"
        normalized.append(
            {
                "title": str(item.get("title") or item.get("forum") or item.get("name") or url).strip(),
                "url": url,
                "description": str(item.get("description") or item.get("key_info") or "").strip(),
                "type": link_type,
            }
        )
    return normalized


def extract_videos(links: list[dict] | None) -> list[dict]:
    return [item for item in _normalize_links(links) if item.get("type") == "video" or any(domain in item.get("url", "").lower() for domain in VIDEO_DOMAINS)]


def classify_feedback(message_type: str, text: str) -> str:
    lowered = " ".join(str(text or "").lower().split())
    message_type = str(message_type or "").lower()
    if message_type == "feedback_helped" or any(word in lowered for word in ("помогло", "решено", "helped", "fixed", "solved")):
        return "helped"
    if message_type in {"feedback_not_helped", "followup_deep"}:
        return "not_helped"
    if any(word in lowered for word in ("мало", "подробнее", "глубже", "more", "deeper", "details")):
        return "need_more"
    if any(word in lowered for word in ("не та машина", "wrong car")):
        return "wrong_car"
    if any(word in lowered for word in ("неверно", "ошибка", "wrong answer")):
        return "wrong_answer"
    return ""


def _vehicle_match_score(vehicle: dict, car_text: str) -> int:
    text = " ".join(str(car_text or "").lower().split())
    if not text:
        return 0

    fields = {
        "brand": str(vehicle.get("brand") or "").lower(),
        "model": str(vehicle.get("model") or "").lower(),
        "engine": str(vehicle.get("engine") or "").lower(),
        "year": str(vehicle.get("year") or "").lower(),
        "nickname": str(vehicle.get("nickname") or "").lower(),
        "vin": str(vehicle.get("vin") or "").lower(),
    }

    score = 0
    for key, value in fields.items():
        if not value:
            continue
        if value in text:
            score += 4 if key in {"brand", "model"} else 2
        elif any(part and part in text for part in value.replace("-", " ").split()):
            score += 1
    return score


def resolve_user_vehicle(*, user_id: int | None, car_text: str) -> dict | None:
    if user_id is None:
        return None

    def operation():
        response = (
            get_supabase_client()
            .table("vehicles")
            .select("*")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .limit(50)
            .execute()
        )
        vehicles = _rows(response)
        if not vehicles:
            return None

        scored = sorted(
            ((vehicle, _vehicle_match_score(vehicle, car_text)) for vehicle in vehicles),
            key=lambda item: item[1],
            reverse=True,
        )
        best_vehicle, best_score = scored[0]
        if best_score >= 2:
            return best_vehicle
        if len(vehicles) == 1 and not str(car_text or "").strip():
            return vehicles[0]
        return None

    return _safe_execute(operation)


def get_active_conversation(*, user_id: int | None, vehicle_id: int | None = None, title: str = "") -> dict | None:
    if user_id is None:
        return None

    def operation():
        client = get_supabase_client()
        response = (
            client.table("conversations")
            .select("*")
            .eq("user_id", user_id)
            .eq("status", "active")
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = _rows(response)
        if rows:
            row = rows[0]
            updates: dict[str, Any] = {"last_message_at": _now_iso(), "updated_at": _now_iso()}
            if vehicle_id and not row.get("vehicle_id"):
                updates["vehicle_id"] = vehicle_id
            updated = client.table("conversations").update(updates).eq("id", row["id"]).execute()
            return (_rows(updated) or [row])[0]

        payload = {
            "user_id": user_id,
            "vehicle_id": vehicle_id,
            "channel": "site",
            "status": "active",
            "title": title[:160] if title else "",
            "last_message_at": _now_iso(),
        }
        created = client.table("conversations").insert(payload).execute()
        created_rows = _rows(created)
        return created_rows[0] if created_rows else None

    return _safe_execute(operation)


def save_message(*, conversation_id: int | None, user_id: int | None, vehicle_id: int | None, role: str, text: str, language: str) -> dict | None:
    if conversation_id is None or user_id is None or not str(text or "").strip():
        return None

    def operation():
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

    return _safe_execute(operation)


def save_diagnostic_event(
    *,
    user_id: int | None,
    conversation_id: int | None,
    vehicle_id: int | None,
    vehicle_profile_id: int | None,
    question: str,
    answer: str,
    language: str,
    status: str,
    message_type: str,
    parser_used: bool = False,
    deep_search_used: bool = False,
    cost_counted: bool = False,
    links: list[dict] | None = None,
) -> dict | None:
    if user_id is None or message_type == "greeting":
        return None

    normalized_links = _normalize_links(links)
    videos = extract_videos(normalized_links)

    def operation():
        payload = {
            "user_id": user_id,
            "vehicle_id": vehicle_id,
            "vehicle_profile_id": vehicle_profile_id,
            "conversation_id": conversation_id,
            "question": str(question or "").strip(),
            "raw_question": str(question or "").strip(),
            "symptoms": str(question or "").strip(),
            "answer": str(answer or "").strip(),
            "language": language or "ru",
            "request_type": "deep_search" if deep_search_used else "parser" if parser_used else "text",
            "status": status,
            "source": "web",
            "parser_used": parser_used,
            "deep_search_used": deep_search_used,
            "request_cost_counted": cost_counted,
            "sources": normalized_links,
            "videos": videos,
            "updated_at": _now_iso(),
        }
        response = get_supabase_client().table("diagnostic_requests").insert(payload).execute()
        rows = _rows(response)
        return rows[0] if rows else None

    return _safe_execute(operation)


def save_parser_run(
    *,
    user_id: int | None,
    conversation_id: int | None,
    vehicle_id: int | None,
    diagnostic_request_id: int | None,
    run_type: str,
    query: str,
    parsed_case: dict,
) -> dict | None:
    if user_id is None:
        return None
    links = _normalize_links(parsed_case.get("links") if isinstance(parsed_case, dict) else [])
    raw = parsed_case.get("_raw") if isinstance(parsed_case, dict) else {}
    meta = raw.get("_meta") if isinstance(raw, dict) else {}
    forums_used = parsed_case.get("forums_found") if isinstance(parsed_case, dict) else None
    if not forums_used and isinstance(raw, dict):
        forums_used = raw.get("forums_found")

    def operation():
        payload = {
            "user_id": user_id,
            "vehicle_id": vehicle_id,
            "conversation_id": conversation_id,
            "diagnostic_request_id": diagnostic_request_id,
            "run_type": run_type,
            "query_original": query,
            "query_translated": raw.get("query_translated") if isinstance(raw, dict) else None,
            "languages_used": raw.get("languages_used") if isinstance(raw, dict) else None,
            "forums_used": forums_used,
            "sources_found": links,
            "videos_found": extract_videos(links),
            "tokens_used": meta.get("tokens_used") if isinstance(meta, dict) else None,
        }
        response = get_supabase_client().table("parser_runs").insert(payload).execute()
        rows = _rows(response)
        return rows[0] if rows else None

    return _safe_execute(operation)


def save_video_library(*, user_id: int | None, vehicle_id: int | None, diagnostic_request_id: int | None, links: list[dict] | None, topic: str) -> None:
    if user_id is None:
        return
    videos = extract_videos(links)
    if not videos:
        return

    def operation():
        client = get_supabase_client()
        for item in videos:
            client.table("video_library").insert(
                {
                    "user_id": user_id,
                    "vehicle_id": vehicle_id,
                    "diagnostic_request_id": diagnostic_request_id,
                    "title": item.get("title") or "Video",
                    "url": item.get("url"),
                    "platform": "youtube" if "youtu" in item.get("url", "").lower() else "browser",
                    "topic": topic,
                }
            ).execute()
        return None

    _safe_execute(operation)


def save_feedback(*, user_id: int | None, vehicle_id: int | None, conversation_id: int | None, diagnostic_request_id: int | None, feedback_type: str, feedback_text: str) -> dict | None:
    if user_id is None or not feedback_type:
        return None

    def operation():
        response = get_supabase_client().table("user_feedback").insert(
            {
                "user_id": user_id,
                "vehicle_id": vehicle_id,
                "conversation_id": conversation_id,
                "diagnostic_request_id": diagnostic_request_id,
                "feedback_type": feedback_type,
                "feedback_text": feedback_text,
            }
        ).execute()
        rows = _rows(response)
        return rows[0] if rows else None

    return _safe_execute(operation)


def create_solved_case(
    *,
    user_id: int | None,
    vehicle_id: int | None,
    diagnostic_request_id: int | None,
    car_info: str,
    symptoms: str,
    confirmed_problem: str,
    confirmed_solution: str,
    links: list[dict] | None,
) -> dict | None:
    if user_id is None:
        return None
    normalized_links = _normalize_links(links)

    def operation():
        client = get_supabase_client()
        if diagnostic_request_id:
            client.table("diagnostic_requests").update({"status": "resolved", "updated_at": _now_iso()}).eq("id", diagnostic_request_id).execute()
        payload = {
            "user_id": user_id,
            "vehicle_id": vehicle_id,
            "diagnostic_request_id": diagnostic_request_id,
            "brand": car_info,
            "symptoms": symptoms,
            "confirmed_problem": confirmed_problem,
            "confirmed_solution": confirmed_solution,
            "sources": normalized_links,
            "videos": extract_videos(normalized_links),
            "confidence": 0.7,
        }
        response = client.table("solved_cases").insert(payload).execute()
        rows = _rows(response)
        return rows[0] if rows else None

    return _safe_execute(operation)


def get_latest_answered_diagnostic_request(*, user_id: int | None, conversation_id: int | None = None, exclude_id: int | None = None) -> dict | None:
    if user_id is None:
        return None

    def operation():
        query = (
            get_supabase_client()
            .table("diagnostic_requests")
            .select("id,user_id,vehicle_id,conversation_id,question,raw_question,symptoms,answer,sources,videos,parser_used,deep_search_used,status,created_at")
            .eq("user_id", user_id)
            .in_("status", ["answered", "need_deep_search", "not_resolved"])
            .order("created_at", desc=True)
            .limit(10)
        )
        if conversation_id:
            query = query.eq("conversation_id", conversation_id)
        response = query.execute()
        for row in _rows(response):
            if exclude_id and row.get("id") == exclude_id:
                continue
            if str(row.get("answer") or "").strip():
                return row
        return None

    return _safe_execute(operation)


def create_solved_case_from_diagnostic(
    *,
    user_id: int | None,
    vehicle_id: int | None,
    diagnostic_request: dict | None,
    car_info: str,
) -> dict | None:
    if not diagnostic_request:
        return None
    return create_solved_case(
        user_id=user_id,
        vehicle_id=vehicle_id or diagnostic_request.get("vehicle_id"),
        diagnostic_request_id=diagnostic_request.get("id"),
        car_info=car_info,
        symptoms=str(diagnostic_request.get("symptoms") or diagnostic_request.get("raw_question") or diagnostic_request.get("question") or ""),
        confirmed_problem=str(diagnostic_request.get("symptoms") or diagnostic_request.get("question") or ""),
        confirmed_solution=str(diagnostic_request.get("answer") or ""),
        links=diagnostic_request.get("sources") or [],
    )
