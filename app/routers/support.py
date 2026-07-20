from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.database.supabase import SupabaseOperationError, SupabaseUnavailableError
from app.services.support_service import (
    SUPPORT_EMAIL,
    SUPPORT_MAX_IMAGES,
    create_support_request,
    send_support_email,
    update_support_request_status,
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
    attachments = images or []
    try:
        uploaded_attachments = await upload_support_images(files=attachments, auth_user_id=auth_user_id)
        row = create_support_request(
            auth_user_id=auth_user_id,
            email=email,
            subject=subject,
            message=message,
            attachments=uploaded_attachments,
        )
        send_support_email(row=row, attachments=uploaded_attachments)
        update_support_request_status(request_id=str(row.get("id") or ""), status="emailed")
        row["status"] = "emailed"
    except HTTPException:
        raise
    except SupabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SupabaseOperationError as exc:
        request_id = str(locals().get("row", {}).get("id") or "").strip()
        if request_id:
            try:
                update_support_request_status(request_id=request_id, status="email_failed")
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "ok": True,
        "id": row.get("id"),
        "status": row.get("status") or "new",
        "attachment_urls": [item.public_url for item in uploaded_attachments],
        "support_email": SUPPORT_EMAIL,
        "max_images": SUPPORT_MAX_IMAGES,
    }
