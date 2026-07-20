from __future__ import annotations

import json
import mimetypes
import re
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from app.database.supabase import SupabaseOperationError, SupabaseUnavailableError, get_supabase_client

SUPPORT_BUCKET = "support-attachments"
SUPPORT_EMAIL = "pulscar.ai@gmail.com"
SUPPORT_MAX_IMAGES = 3
SUPPORT_MAX_IMAGE_BYTES = 5 * 1024 * 1024
SUPPORT_ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}


def _clean_text(value: str) -> str:
    return str(value or "").strip()


def _safe_file_name(name: str) -> str:
    base = re.sub(r"\.[a-z0-9]+$", "", _clean_text(name), flags=re.IGNORECASE)
    base = re.sub(r"[^a-zA-Z0-9._-]+", "-", base).strip("-._")
    return base or "attachment"


def _normalized_mime_type(file: UploadFile) -> str:
    mime_type = _clean_text(getattr(file, "content_type", "")).lower()
    if mime_type == "image/jpg":
        return "image/jpeg"
    if mime_type:
        return mime_type
    guessed, _ = mimetypes.guess_type(_clean_text(getattr(file, "filename", "")))
    return _clean_text(guessed).lower()


def _file_extension(file: UploadFile, mime_type: str) -> str:
    file_name = _clean_text(getattr(file, "filename", ""))
    if "." in file_name:
        extension = file_name.rsplit(".", 1)[-1].lower()
        if extension == "jpeg":
            return "jpg"
        if extension:
            return extension
    if mime_type == "image/png":
        return "png"
    if mime_type == "image/webp":
        return "webp"
    return "jpg"


def _user_path_segment(auth_user_id: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", _clean_text(auth_user_id)).strip("-")
    return cleaned or "guest"


def _ensure_support_bucket() -> None:
    client = get_supabase_client()
    try:
        client.storage.get_bucket(SUPPORT_BUCKET)
        return
    except Exception:
        pass

    try:
        client.storage.create_bucket(
            SUPPORT_BUCKET,
            options={
                "public": True,
                "allowed_mime_types": sorted(SUPPORT_ALLOWED_MIME_TYPES),
            },
        )
    except Exception as exc:
        message = str(exc or "").lower()
        if "already exists" not in message and "duplicate" not in message:
            raise SupabaseOperationError(f"Failed to create support storage bucket: {exc}") from exc


async def upload_support_images(*, files: list[UploadFile], auth_user_id: str = "") -> list[str]:
    if len(files) > SUPPORT_MAX_IMAGES:
        raise HTTPException(status_code=400, detail=f"Up to {SUPPORT_MAX_IMAGES} images are allowed.")

    if not files:
        return []

    _ensure_support_bucket()
    client = get_supabase_client()
    uploaded_urls: list[str] = []
    date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    user_segment = _user_path_segment(auth_user_id)

    for file in files:
        if not file or not _clean_text(getattr(file, "filename", "")):
            continue

        mime_type = _normalized_mime_type(file)
        if mime_type not in SUPPORT_ALLOWED_MIME_TYPES:
            raise HTTPException(status_code=400, detail="Only JPG, JPEG, PNG, and WEBP images are allowed.")

        content = await file.read()
        if not content:
            continue
        if len(content) > SUPPORT_MAX_IMAGE_BYTES:
            raise HTTPException(status_code=400, detail="Each image must be 5 MB or smaller.")

        safe_name = _safe_file_name(getattr(file, "filename", "attachment"))
        extension = _file_extension(file, mime_type)
        object_path = f"{user_segment}/{date_prefix}/{uuid4().hex}-{safe_name}.{extension}"

        try:
            client.storage.from_(SUPPORT_BUCKET).upload(
                object_path,
                content,
                {
                    "content-type": mime_type,
                    "cache-control": "3600",
                    "upsert": "false",
                },
            )
        except Exception as exc:
            raise SupabaseOperationError(f"Failed to upload support attachment: {exc}") from exc
        finally:
            await file.close()

        public_url = str(client.storage.from_(SUPPORT_BUCKET).get_public_url(object_path) or "").strip()
        if not public_url:
            raise SupabaseOperationError("Support attachment uploaded but public URL was not returned.")
        uploaded_urls.append(public_url)

    return uploaded_urls


def create_support_request(
    *,
    auth_user_id: str = "",
    email: str,
    subject: str,
    message: str,
    attachment_urls: list[str] | None = None,
) -> dict:
    cleaned_email = _clean_text(email)
    cleaned_subject = _clean_text(subject)
    cleaned_message = _clean_text(message)
    cleaned_auth_user_id = _clean_text(auth_user_id)

    if not cleaned_email:
        raise HTTPException(status_code=400, detail="Email is required.")
    if not cleaned_subject:
        raise HTTPException(status_code=400, detail="Subject is required.")
    if not cleaned_message:
        raise HTTPException(status_code=400, detail="Message is required.")

    payload = {
        "user_id": cleaned_auth_user_id or None,
        "email": cleaned_email,
        "subject": cleaned_subject,
        "message": cleaned_message,
        "attachment_url": json.dumps(attachment_urls or [], ensure_ascii=False) if attachment_urls else None,
        "status": "new",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        response = get_supabase_client().table("support_requests").insert(payload).execute()
        rows = getattr(response, "data", []) or []
        if not rows:
            raise SupabaseOperationError("Support request insert returned no rows.")
        return rows[0]
    except HTTPException:
        raise
    except SupabaseOperationError:
        raise
    except SupabaseUnavailableError:
        raise
    except Exception as exc:
        raise SupabaseOperationError(f"Failed to create support request: {exc}") from exc
