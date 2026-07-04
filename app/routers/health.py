from fastapi import APIRouter

from app.database.supabase import (
    get_supabase_client,
    is_supabase_configured,
    is_supabase_service_key_configured,
    supabase_key_source,
)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    supabase_read_ok = False
    supabase_error = ""
    if is_supabase_configured():
        try:
            get_supabase_client().table("users").select("id").limit(1).execute()
            supabase_read_ok = True
        except Exception as exc:
            supabase_error = str(exc)[:240]

    return {
        "status": "ok",
        "supabase": {
            "configured": is_supabase_configured(),
            "read_ok": supabase_read_ok,
            "service_key": is_supabase_service_key_configured(),
            "key_source": supabase_key_source(),
            "error": supabase_error,
        },
    }
