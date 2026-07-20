from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.database.supabase import SupabaseOperationError, SupabaseUnavailableError
from app.services.support_service import (
    SUPPORT_EMAIL,
    SUPPORT_MAX_IMAGES,
    create_support_request,
    upload_support_images,
)

router = APIRouter(prefix="/api", tags=["support"])


@router.post("/support")
async def support_request(
    email: str = Form(default=""),
    subject: str = Form(default=""),
    message: str = Form(default=""),
    auth_user_id: str = Form(default=""),
    images: list[UploadFile] | None = File(default=None),
):
    files = images or []
    try:
        attachment_urls = await upload_support_images(files=files, auth_user_id=auth_user_id)
        row = create_support_request(
            auth_user_id=auth_user_id,
            email=email,
            subject=subject,
            message=message,
            attachment_urls=attachment_urls,
        )
    except HTTPException:
        raise
    except SupabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SupabaseOperationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "ok": True,
        "id": row.get("id"),
        "status": row.get("status") or "new",
        "attachment_urls": attachment_urls,
        "support_email": SUPPORT_EMAIL,
        "max_images": SUPPORT_MAX_IMAGES,
    }
