from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.database.supabase import SupabaseOperationError, SupabaseUnavailableError, get_supabase_client, is_supabase_configured
from app.services.conversation_service import get_or_create_conversation as ensure_conversation
from app.services.conversation_service import save_message as persist_message
from app.services.diagnostic_service import create_diagnostic_request
from app.services.feedback_service import create_feedback
from app.services.link_service import extract_videos, normalize_links
from app.services.parser_run_service import create_parser_run

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


def classify_feedback(message_type: str, text: str) -> str:
    lowered = " ".join(str(text or "").lower().split())
    message_type = str(message_type or "").lower()
    if message_type in {"feedback_not_helped", "followup_deep"}:
        return "not_helped"
    if any(word in lowered for word in ("не помогло", "не помог", "не помогла", "not helped", "did not help", "didn't help", "does not help", "no help")):
        return "not_helped"
    if any(word in lowered for word in ("мало", "подробнее", "глубже", "больше", "more", "deeper", "details")):
        return "need_more"
    if any(word in lowered for word in ("не та машина", "другая машина", "wrong car")):
        return "wrong_car"
    if any(word in lowered for word in ("неверно", "ошибка", "wrong answer")):
        return "wrong_answer"
    if message_type == "feedback_helped" or any(word in lowered for word in ("помогло", "помог", "решено", "helped", "fixed", "solved")):
        return "helped"
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


def list_user_vehicles(*, user_id: int | None) -> list[dict]:
    if user_id is None:
        return []

    def operation():
        response = (
            get_supabase_client()
            .table("vehicles")
            .select("*")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .limit(100)
            .execute()
        )
        return _rows(response)

    return _safe_execute(operation, [])


def save_user_vehicle(*, user_id: int | None, vehicle_id: int | None, payload: dict[str, Any]) -> dict | None:
    if user_id is None:
        return None

    clean_payload = {key: value for key, value in payload.items() if value is not None}
    clean_payload["user_id"] = user_id
    clean_payload["updated_at"] = _now_iso()

    def operation():
        client = get_supabase_client()
        if vehicle_id:
            response = (
                client.table("vehicles")
                .update(clean_payload)
                .eq("id", vehicle_id)
                .eq("user_id", user_id)
                .execute()
            )
        else:
            response = client.table("vehicles").insert(clean_payload).execute()
        rows = _rows(response)
        return rows[0] if rows else None

    return _safe_execute(operation)


def delete_user_vehicle(*, user_id: int | None, vehicle_id: int | None) -> bool:
    if user_id is None or vehicle_id is None:
        return False

    def operation():
        get_supabase_client().table("vehicles").delete().eq("id", vehicle_id).eq("user_id", user_id).execute()
        return True

    return bool(_safe_execute(operation, False))


def _vehicle_snapshot_from_text(car_info: str) -> dict[str, Any]:
    text = " ".join(str(car_info or "").split())
    year_match = re.search(r"\b(19[8-9]\d|20[0-3]\d)\b", text)
    engine_match = re.search(
        r"\b(1g[- ]?gze|1ggze|sr20vet|qr20|qr25|2gr|1gr|ej20|ej25|k20|k24|m57|n52|n54|n55|b58)\b",
        text,
        re.IGNORECASE,
    )
    brand_match = re.search(
        r"\b(toyota|nissan|honda|mazda|subaru|mitsubishi|lexus|infiniti|bmw|mercedes(?:-benz)?|audi|volkswagen|ford|hyundai|kia)\b",
        text,
        re.IGNORECASE,
    )
    words = text.split()
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


def _vehicle_snapshot_from_row(row: dict | None, car_info: str) -> dict[str, Any]:
    fallback = _vehicle_snapshot_from_text(car_info)
    if not row:
        return fallback
    return {
        "brand": row.get("brand") or fallback["brand"],
        "model": row.get("model") or fallback["model"],
        "year": row.get("year") or fallback["year"],
        "engine": row.get("engine") or fallback["engine"],
    }


def get_active_conversation(*, user_id: int | None, vehicle_id: int | None = None, title: str = "") -> dict | None:
    if user_id is None:
        return None
    return ensure_conversation(
        user_id=user_id,
        vehicle_id=vehicle_id,
        title=title,
        force_new_context=False,
    )


def save_message(*, conversation_id: int | None, user_id: int | None, vehicle_id: int | None, role: str, text: str, language: str) -> dict | None:
    return persist_message(
        conversation_id=conversation_id,
        user_id=user_id,
        vehicle_id=vehicle_id,
        role=role,
        text=text,
        language=language,
    )


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

    normalized_links = normalize_links(links)
    return create_diagnostic_request(
        user_id=user_id,
        conversation_id=conversation_id,
        vehicle_id=vehicle_id,
        question=str(question or "").strip(),
        answer=str(answer or "").strip(),
        language=language or "ru",
        request_type="deep_search" if deep_search_used else "parser" if parser_used else "text",
        status=status,
        parser_used=parser_used,
        deep_search_used=deep_search_used,
        request_cost_counted=cost_counted,
        sources=normalized_links,
        videos=extract_videos(normalized_links),
    )


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
    return create_parser_run(
        user_id=user_id,
        vehicle_id=vehicle_id,
        conversation_id=conversation_id,
        diagnostic_request_id=diagnostic_request_id,
        run_type=run_type,
        query_original=query,
        parsed_case=parsed_case,
    )


def save_video_library(*, user_id: int | None, vehicle_id: int | None, diagnostic_request_id: int | None, links: list[dict] | None, topic: str) -> None:
    if user_id is None:
        return
    videos = extract_videos(links)
    if not videos:
        return

    def operation():
        client = get_supabase_client()
        for item in videos:
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            exists = (
                client.table("video_library")
                .select("id")
                .eq("user_id", user_id)
                .eq("url", url)
                .limit(1)
                .execute()
            )
            if _rows(exists):
                continue
            client.table("video_library").insert(
                {
                    "user_id": user_id,
                    "vehicle_id": vehicle_id,
                    "diagnostic_request_id": diagnostic_request_id,
                    "title": item.get("title") or "Video",
                    "url": url,
                    "platform": "youtube" if "youtu" in url.lower() else "browser",
                    "topic": topic,
                }
            ).execute()
        return None

    _safe_execute(operation)


def save_feedback(*, user_id: int | None, vehicle_id: int | None, conversation_id: int | None, diagnostic_request_id: int | None, feedback_type: str, feedback_text: str) -> dict | None:
    return create_feedback(
        user_id=user_id,
        vehicle_id=vehicle_id,
        conversation_id=conversation_id,
        diagnostic_request_id=diagnostic_request_id,
        feedback_type=feedback_type,
        feedback_text=feedback_text,
    )


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
    normalized_links = normalize_links(links)

    def operation():
        client = get_supabase_client()
        if diagnostic_request_id:
            client.table("diagnostic_requests").update({"status": "solved", "updated_at": _now_iso()}).eq("id", diagnostic_request_id).execute()
        vehicle_row = None
        if vehicle_id:
            vehicle_response = client.table("vehicles").select("brand,model,year,engine").eq("id", vehicle_id).limit(1).execute()
            vehicle_rows = _rows(vehicle_response)
            vehicle_row = vehicle_rows[0] if vehicle_rows else None
        snapshot = _vehicle_snapshot_from_row(vehicle_row, car_info)
        payload = {
            "user_id": user_id,
            "vehicle_id": vehicle_id,
            "diagnostic_request_id": diagnostic_request_id,
            "brand": snapshot.get("brand") or car_info,
            "model": snapshot.get("model") or None,
            "year": snapshot.get("year") or None,
            "engine": snapshot.get("engine") or None,
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
        car_info=(
            car_info
            if (vehicle_id or diagnostic_request.get("vehicle_id"))
            else str(
                diagnostic_request.get("raw_question")
                or diagnostic_request.get("question")
                or diagnostic_request.get("symptoms")
                or car_info
            )
        ),
        symptoms=str(diagnostic_request.get("symptoms") or diagnostic_request.get("raw_question") or diagnostic_request.get("question") or ""),
        confirmed_problem=str(diagnostic_request.get("symptoms") or diagnostic_request.get("question") or ""),
        confirmed_solution=str(diagnostic_request.get("answer") or ""),
        links=diagnostic_request.get("sources") or [],
    )
