from __future__ import annotations

import json
import mimetypes
import os
import re
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
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


@dataclass
class SupportAttachment:
    file_name: str
    mime_type: str
    content: bytes
    public_url: str


def _clean_text(value: str) -> str:
    return str(value or "").strip()


def _env_value(name: str) -> str:
    return _clean_text(os.getenv(name, ""))


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


def _support_email_to() -> str:
    return _env_value("SUPPORT_EMAIL_TO") or SUPPORT_EMAIL


def _support_email_from() -> str:
    return _env_value("SUPPORT_EMAIL_FROM") or _smtp_username() or SUPPORT_EMAIL


def _smtp_host() -> str:
    return _env_value("SUPPORT_SMTP_HOST") or "smtp.gmail.com"


def _smtp_port() -> int:
    raw_port = _env_value("SUPPORT_SMTP_PORT") or "587"
    try:
        return max(int(raw_port), 1)
    except Exception:
        return 587


def _smtp_username() -> str:
    return _env_value("SUPPORT_SMTP_USERNAME") or SUPPORT_EMAIL


def _smtp_password() -> str:
    return _env_value("SUPPORT_SMTP_PASSWORD")


def _smtp_use_tls() -> bool:
    value = (_env_value("SUPPORT_SMTP_USE_TLS") or "true").lower()
    return value not in {"0", "false", "no", "off"}


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


async def upload_support_images(*, files: list[UploadFile], auth_user_id: str = "") -> list[SupportAttachment]:
    if len(files) > SUPPORT_MAX_IMAGES:
        raise HTTPException(status_code=400, detail=f"Up to {SUPPORT_MAX_IMAGES} images are allowed.")

    if not files:
        return []

    _ensure_support_bucket()
    client = get_supabase_client()
    uploaded_files: list[SupportAttachment] = []
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
        uploaded_files.append(
            SupportAttachment(
                file_name=f"{safe_name}.{extension}",
                mime_type=mime_type,
                content=content,
                public_url=public_url,
            )
        )

    return uploaded_files


def _attachment_urls(attachments: list[SupportAttachment] | None) -> list[str]:
    return [attachment.public_url for attachment in attachments or [] if _clean_text(attachment.public_url)]


def create_support_request(
    *,
    auth_user_id: str = "",
    email: str,
    subject: str,
    message: str,
    attachments: list[SupportAttachment] | None = None,
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
        "attachment_url": json.dumps(_attachment_urls(attachments), ensure_ascii=False) if attachments else None,
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


def update_support_request_status(*, request_id: str, status: str) -> None:
    cleaned_request_id = _clean_text(request_id)
    cleaned_status = _clean_text(status)
    if not cleaned_request_id or not cleaned_status:
        return
    try:
        get_supabase_client().table("support_requests").update({"status": cleaned_status}).eq("id", cleaned_request_id).execute()
    except Exception as exc:
        raise SupabaseOperationError(f"Failed to update support request status: {exc}") from exc


def send_support_email(*, row: dict, attachments: list[SupportAttachment] | None = None) -> None:
    smtp_password = _smtp_password()
    if not smtp_password:
        raise SupabaseOperationError(
            "Support request was saved, but email forwarding is not configured. Set SUPPORT_SMTP_PASSWORD in Render."
        )

    support_to = _support_email_to()
    support_from = _support_email_from()
    smtp_username = _smtp_username()
    subject = _clean_text(row.get("subject")) or "Support request"
    requester_email = _clean_text(row.get("email"))
    requester_message = _clean_text(row.get("message"))
    created_at = _clean_text(row.get("created_at")) or datetime.now(timezone.utc).isoformat()
    request_id = _clean_text(row.get("id"))
    user_id = _clean_text(row.get("user_id"))
    attachment_urls = _attachment_urls(attachments)

    message = EmailMessage()
    message["Subject"] = f"[PULS Support] {subject}"
    message["From"] = support_from
    message["To"] = support_to
    if requester_email:
        message["Reply-To"] = requester_email

    lines = [
        "New PULS support request",
        "",
        f"Request ID: {request_id or '-'}",
        f"Created at: {created_at}",
        f"User ID: {user_id or 'guest'}",
        f"Requester email: {requester_email or '-'}",
        f"Subject: {subject}",
        "",
        "Message:",
        requester_message or "-",
    ]
    if attachment_urls:
        lines.extend(["", "Attachment URLs:"])
        lines.extend(attachment_urls)
    message.set_content("\n".join(lines))

    html_parts = [
        "<h2>New PULS support request</h2>",
        "<ul>",
        f"<li><strong>Request ID:</strong> {request_id or '-'}</li>",
        f"<li><strong>Created at:</strong> {created_at}</li>",
        f"<li><strong>User ID:</strong> {user_id or 'guest'}</li>",
        f"<li><strong>Requester email:</strong> {requester_email or '-'}</li>",
        f"<li><strong>Subject:</strong> {subject}</li>",
        "</ul>",
        "<p><strong>Message:</strong></p>",
        f"<pre style=\"white-space:pre-wrap;font-family:Arial,sans-serif\">{requester_message or '-'}</pre>",
    ]
    if attachment_urls:
        html_parts.append("<p><strong>Attachment URLs:</strong></p><ul>")
        html_parts.extend(f"<li><a href=\"{url}\">{url}</a></li>" for url in attachment_urls)
        html_parts.append("</ul>")
    if attachment_urls:
        html_parts.append("<p><strong>Attached images preview:</strong></p>")
        html_parts.extend(
            f"<p><img src=\"{attachment.public_url}\" alt=\"{attachment.file_name}\" style=\"max-width:720px;height:auto;border:1px solid #d0d7de\"></p>"
            for attachment in attachments or []
        )
    message.add_alternative("".join(html_parts), subtype="html")

    for attachment in attachments or []:
        maintype, _, subtype = attachment.mime_type.partition("/")
        message.add_attachment(
            attachment.content,
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=attachment.file_name,
        )

    try:
        if _smtp_port() == 465:
            with smtplib.SMTP_SSL(_smtp_host(), _smtp_port(), timeout=30) as smtp:
                if smtp_username:
                    smtp.login(smtp_username, smtp_password)
                smtp.send_message(message)
            return

        with smtplib.SMTP(_smtp_host(), _smtp_port(), timeout=30) as smtp:
            smtp.ehlo()
            if _smtp_use_tls():
                smtp.starttls()
                smtp.ehlo()
            if smtp_username:
                smtp.login(smtp_username, smtp_password)
            smtp.send_message(message)
    except Exception as exc:
        raise SupabaseOperationError(f"Support request was saved, but email forwarding failed: {exc}") from exc
