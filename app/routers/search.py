from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.database.supabase import get_supabase_client, rows
from app.services.auth_service import get_or_create_profile
from app.services import v2_repository as repo

router = APIRouter(prefix="/api", tags=["research"])


@router.get("/problems/{problem_id}/research")
async def problem_research(problem_id: int, request: Request) -> dict:
    user = await get_or_create_profile(request=request, require_auth=True)
    problem = repo.get_problem(user_id=user.id, problem_id=problem_id)
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found.")
    episodes = rows(
        get_supabase_client()
        .table("search_episodes")
        .select("*, search_runs(*)")
        .eq("user_id", user.id)
        .eq("problem_id", problem_id)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    return {"episodes": episodes}
