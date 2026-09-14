from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse, urlunparse
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


def _canonical_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    if "youtu.be" in netloc:
        video_id = path.strip("/").split("/", 1)[0]
        return f"https://www.youtube.com/watch?v={video_id}" if video_id else raw
    if "youtube.com" in netloc:
        video_id = parse_qs(parsed.query).get("v", [""])[0]
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"
        if path.startswith("/shorts/"):
            video_id = path.strip("/").split("/", 1)[1] if "/" in path.strip("/") else ""
            return f"https://www.youtube.com/watch?v={video_id}" if video_id else raw
    return urlunparse((scheme, netloc, path, "", "", ""))


def _youtube_video_id(url: str) -> str:
    canonical = _canonical_url(url)
    parsed = urlparse(canonical)
    if "youtube.com" not in parsed.netloc.lower():
        return ""
    return parse_qs(parsed.query).get("v", [""])[0]


def _reference_media_type(link_type: str) -> str:
    value = str(link_type or "").strip().lower()
    if value in {"image", "photo", "picture"}:
        return "image"
    if value == "video":
        return "video"
    if value in {"manual", "document", "pdf"}:
        return "document"
    return "webpage"


def _reference_platform(url: str, link_type: str) -> str:
    lowered = str(url or "").lower()
    if "youtube.com" in lowered or "youtu.be" in lowered:
        return "youtube"
    if any(term in str(link_type or "").lower() for term in ("manual", "document")):
        return "manufacturer"
    return "web"


def _relevance_score(*, link: dict, subject: str, reference_target: str) -> float:
    haystack = " ".join(
        str(link.get(key) or "").lower()
        for key in ("title", "description", "url", "type")
    )
    needles = [
        token
        for token in " ".join(part for part in (subject, reference_target) if part).lower().replace("_", " ").split()
        if len(token) > 3
    ]
    if not needles:
        return 0.5
    matches = sum(1 for token in needles if token in haystack)
    return min(1.0, matches / max(len(needles), 1))


def _reference_link_from_row(row: dict) -> dict:
    return {
        "title": str(row.get("title") or row.get("canonical_url") or "").strip(),
        "url": str(row.get("canonical_url") or "").strip(),
        "description": str(row.get("description") or "").strip(),
        "type": str(row.get("media_type") or "webpage").strip(),
    }


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
            canonical = _canonical_url(url)
            exists = (
                client.table("video_library")
                .select("id")
                .eq("user_id", user_id)
                .eq("url", canonical or url)
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
                    "url": canonical or url,
                    "platform": "youtube" if "youtu" in (canonical or url).lower() else "browser",
                    "topic": topic,
                }
            ).execute()
        return None

    _safe_execute(operation)


def find_reusable_media(
    *,
    user_id: int | None,
    vehicle_id: int | None,
    subject: str,
    intent: str,
    limit: int = 5,
) -> list[dict]:
    if user_id is None:
        return []

    subject_text = " ".join(str(subject or "").lower().split())
    wants_video = intent == "VIDEO_REFERENCE"
    wants_image = intent == "IMAGE_REFERENCE"

    def score(text: str) -> int:
        haystack = " ".join(str(text or "").lower().split())
        if not subject_text:
            return 1
        value = 0
        if subject_text and subject_text in haystack:
            value += 5
        for token in subject_text.split():
            if len(token) > 3 and token in haystack:
                value += 1
        return value

    def operation():
        client = get_supabase_client()
        candidates: list[dict] = []

        shared_query = client.table("reference_media").select(
            "id,media_type,platform,canonical_url,title,description,subject,reference_target,brand,model,generation,engine,relevance,updated_at"
        )
        if wants_video:
            shared_query = shared_query.eq("media_type", "video")
        elif wants_image:
            shared_query = shared_query.eq("media_type", "image")
        shared_rows = _rows(shared_query.order("updated_at", desc=True).limit(50).execute())
        for row in shared_rows:
            link = _reference_link_from_row(row)
            applicability = " ".join(
                str(row.get(key) or "")
                for key in ("subject", "reference_target", "brand", "model", "generation", "engine", "title", "description")
            )
            row_score = max(score(applicability), int(float(row.get("relevance") or 0) * 5))
            if link["url"] and row_score > 0:
                candidates.append({**link, "_score": row_score + 2})

        video_query = client.table("video_library").select("title,url,platform,topic,vehicle_id,created_at").eq("user_id", user_id)
        if vehicle_id is not None:
            video_query = video_query.eq("vehicle_id", vehicle_id)
        for row in _rows(video_query.order("created_at", desc=True).limit(30).execute()):
            link = {
                "title": str(row.get("title") or "Video").strip(),
                "url": str(row.get("url") or "").strip(),
                "description": str(row.get("topic") or "").strip(),
                "type": "video",
            }
            if link["url"] and (wants_video or not wants_image):
                candidates.append({**link, "_score": score(f"{link['title']} {link['description']}")})

        media_query = client.table("media_files").select("media_type,file_url,thumbnail_url,description,vehicle_id,created_at").eq("user_id", user_id)
        if vehicle_id is not None:
            media_query = media_query.eq("vehicle_id", vehicle_id)
        for row in _rows(media_query.order("created_at", desc=True).limit(50).execute()):
            media_type = str(row.get("media_type") or "link").lower()
            if wants_video and media_type != "video":
                continue
            if wants_image and media_type not in {"image", "photo"}:
                continue
            url = str(row.get("file_url") or "").strip()
            if not url:
                continue
            link = {
                "title": str(row.get("description") or url).strip(),
                "url": url,
                "description": str(row.get("description") or "").strip(),
                "type": "image" if media_type in {"image", "photo"} else "video" if media_type == "video" else "link",
            }
            candidates.append({**link, "_score": score(f"{link['title']} {link['description']} {url}")})

        deduped: dict[str, dict] = {}
        for item in candidates:
            canonical = _canonical_url(item.get("url", ""))
            if not canonical:
                continue
            previous = deduped.get(canonical)
            if previous is None or int(item.get("_score") or 0) > int(previous.get("_score") or 0):
                deduped[canonical] = {**item, "url": canonical}
        ordered = sorted(deduped.values(), key=lambda item: int(item.get("_score") or 0), reverse=True)
        return [{key: value for key, value in item.items() if key != "_score"} for item in ordered if int(item.get("_score") or 0) > 0][:limit]

    return _safe_execute(operation, [])


def upsert_reference_media(
    *,
    user_id: int | None,
    vehicle: dict | None,
    links: list[dict] | None,
    subject: str,
    reference_target: str,
    language: str,
) -> list[dict]:
    if not links:
        return []
    vehicle_context = vehicle or {}

    def operation():
        client = get_supabase_client()
        saved: list[dict] = []
        for link in links:
            if not isinstance(link, dict):
                continue
            url = _canonical_url(str(link.get("url") or "").strip())
            if not url:
                continue
            relevance = _relevance_score(link=link, subject=subject, reference_target=reference_target)
            if relevance <= 0 and (subject or reference_target):
                continue
            media_type = _reference_media_type(str(link.get("type") or ""))
            platform = _reference_platform(url, str(link.get("type") or ""))
            external_id = _youtube_video_id(url) if platform == "youtube" else ""
            existing = client.table("reference_media").select("id").eq("canonical_url", url).limit(1).execute()
            payload = {
                "media_type": media_type,
                "platform": platform,
                "external_id": external_id or None,
                "canonical_url": url,
                "source_url": str(link.get("source_url") or link.get("source") or "").strip() or None,
                "thumbnail_url": str(link.get("thumbnail_url") or link.get("thumbnail") or "").strip() or None,
                "title": str(link.get("title") or "").strip() or None,
                "description": str(link.get("description") or "").strip() or None,
                "language": language or None,
                "vehicle_profile_id": vehicle_context.get("vehicle_profile_id"),
                "brand": vehicle_context.get("brand"),
                "model": vehicle_context.get("model"),
                "generation": vehicle_context.get("generation"),
                "year_from": vehicle_context.get("year"),
                "year_to": vehicle_context.get("year"),
                "engine": vehicle_context.get("engine"),
                "component": None,
                "subject": subject or None,
                "reference_target": reference_target or None,
                "relevance": relevance,
                "metadata": {
                    "provider_type": link.get("type"),
                    "raw": {key: value for key, value in link.items() if key not in {"url", "title", "description"}},
                },
                "discovered_by_user_id": user_id,
                "last_verified_at": _now_iso(),
                "updated_at": _now_iso(),
            }
            rows = _rows(existing)
            if rows:
                response = client.table("reference_media").update(payload).eq("id", rows[0]["id"]).execute()
            else:
                response = client.table("reference_media").insert(payload).execute()
            saved.extend(_rows(response))
        return saved

    return _safe_execute(operation, [])


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
