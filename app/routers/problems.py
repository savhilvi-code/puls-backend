from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from app.services.auth_service import get_or_create_profile
from app.services import v2_repository as repo

router = APIRouter(prefix="/api", tags=["problems"])


class ProblemPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vehicle_id: int
    title: str = ""
    problem_class: str = "OTHER"
    component: str = ""
    status: str = "OPEN"
    symptoms: list[str] = []
    conditions: dict[str, Any] = {}
    confirmed_facts: list[str] = []
    hypotheses: list[dict[str, Any]] = []
    checks_summary: str = ""
    actions_summary: str = ""
    current_conclusion: str = ""
    next_step: str = ""
    mileage: int | None = None
    confirmation: dict[str, Any] = {}


def _problem_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "vehicle_id": row.get("vehicle_id"),
        "title": row.get("title") or "",
        "problem_class": row.get("problem_class") or "OTHER",
        "component": row.get("component") or "",
        "status": row.get("status") or "OPEN",
        "symptoms": row.get("symptoms") or [],
        "conditions": row.get("conditions") or {},
        "confirmed_facts": row.get("confirmed_facts") or [],
        "hypotheses": row.get("hypotheses") or [],
        "checks_summary": row.get("checks_summary") or "",
        "actions_summary": row.get("actions_summary") or "",
        "current_conclusion": row.get("current_conclusion") or "",
        "next_step": row.get("next_step") or "",
        "mileage": row.get("mileage"),
        "first_seen_at": row.get("first_seen_at"),
        "last_seen_at": row.get("last_seen_at"),
        "confirmation": row.get("confirmation") or {},
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _payload_to_db(payload: ProblemPayload) -> dict[str, Any]:
    return {
        "title": payload.title.strip(),
        "problem_class": payload.problem_class.strip() or "OTHER",
        "component": payload.component.strip(),
        "status": payload.status.strip() or "OPEN",
        "symptoms": payload.symptoms,
        "conditions": payload.conditions,
        "confirmed_facts": payload.confirmed_facts,
        "hypotheses": payload.hypotheses,
        "checks_summary": payload.checks_summary.strip(),
        "actions_summary": payload.actions_summary.strip(),
        "current_conclusion": payload.current_conclusion.strip(),
        "next_step": payload.next_step.strip(),
        "mileage": payload.mileage,
        "confirmation": payload.confirmation,
    }


@router.get("/vehicles/{vehicle_id}/timeline")
async def vehicle_timeline(vehicle_id: int, request: Request) -> dict[str, list[dict[str, Any]]]:
    user = await get_or_create_profile(request=request, require_auth=True)
    if not repo.get_vehicle(user_id=user.id, vehicle_id=vehicle_id):
        raise HTTPException(status_code=404, detail="Vehicle not found.")
    return {"events": repo.list_vehicle_events(user_id=user.id, vehicle_id=vehicle_id)}


@router.get("/vehicles/{vehicle_id}/problems")
async def vehicle_problems(vehicle_id: int, request: Request, status: str = "active") -> dict[str, list[dict[str, Any]]]:
    user = await get_or_create_profile(request=request, require_auth=True)
    if not repo.get_vehicle(user_id=user.id, vehicle_id=vehicle_id):
        raise HTTPException(status_code=404, detail="Vehicle not found.")
    statuses = repo.OPEN_PROBLEM_STATUSES if status == "active" else None
    problems = repo.list_problems(user_id=user.id, vehicle_id=vehicle_id, statuses=statuses)
    if status == "closed":
        problems = [item for item in problems if str(item.get("status") or "").upper() in {"SOLVED", "CLOSED", "ARCHIVED"}]
    return {"problems": [_problem_response(item) for item in problems]}


@router.post("/problems")
async def create_problem(payload: ProblemPayload, request: Request) -> dict[str, Any]:
    user = await get_or_create_profile(request=request, require_auth=True)
    if not repo.get_vehicle(user_id=user.id, vehicle_id=payload.vehicle_id):
        raise HTTPException(status_code=404, detail="Vehicle not found.")
    row = repo.save_problem(user_id=user.id, vehicle_id=payload.vehicle_id, payload=_payload_to_db(payload))
    if not row:
        raise HTTPException(status_code=500, detail="Problem was not saved.")
    return {"problem": _problem_response(row)}


@router.get("/problems/{problem_id}")
async def get_problem(problem_id: int, request: Request) -> dict[str, Any]:
    user = await get_or_create_profile(request=request, require_auth=True)
    problem = repo.get_problem(user_id=user.id, problem_id=problem_id)
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found.")
    vehicle = repo.get_vehicle(user_id=user.id, vehicle_id=problem.get("vehicle_id"))
    events = repo.list_vehicle_events(user_id=user.id, vehicle_id=problem.get("vehicle_id"), problem_id=problem_id)
    sources = repo.list_problem_sources(user_id=user.id, problem_id=problem_id)
    return {
        "vehicle": vehicle,
        "problem": _problem_response(problem),
        "events": events,
        "sources": sources,
    }


@router.put("/problems/{problem_id}")
async def update_problem(problem_id: int, payload: ProblemPayload, request: Request) -> dict[str, Any]:
    user = await get_or_create_profile(request=request, require_auth=True)
    existing = repo.get_problem(user_id=user.id, problem_id=problem_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Problem not found.")
    row = repo.save_problem(user_id=user.id, vehicle_id=existing.get("vehicle_id"), problem_id=problem_id, payload=_payload_to_db(payload))
    return {"problem": _problem_response(row or existing)}
