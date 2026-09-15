from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from app.database.supabase import SupabaseOperationError, SupabaseUnavailableError
from app.services.auth_service import get_or_create_profile
from app.services.vehicle_enrichment_service import enrich_vehicle_profile
from app.services import v2_repository as repo

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


class VehiclePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    brand: str = ""
    model: str = ""
    generation: str = ""
    year: int | str | None = None
    engine: str = ""
    fuel: str = ""
    fuel_type: str = ""
    transmission: str = ""
    drive: str = ""
    vin: str = ""
    nickname: str = ""
    mileage: int | str | None = None
    photo_url: str = ""
    country: str = ""
    city: str = ""
    notes: str = ""


def _safe_int(value: int | str | None) -> int | None:
    if value in (None, ""):
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return int(digits) if digits else None


def _payload_to_db(payload: VehiclePayload) -> dict[str, Any]:
    return {
        "brand": payload.brand.strip(),
        "model": payload.model.strip(),
        "generation": payload.generation.strip(),
        "year": _safe_int(payload.year),
        "engine": payload.engine.strip(),
        "fuel": (payload.fuel or payload.fuel_type).strip(),
        "fuel_type": (payload.fuel_type or payload.fuel).strip(),
        "transmission": payload.transmission.strip(),
        "drive": payload.drive.strip(),
        "vin": payload.vin.strip(),
        "nickname": payload.nickname.strip(),
        "mileage": _safe_int(payload.mileage),
        "photo_url": payload.photo_url.strip(),
        "country": payload.country.strip(),
        "city": payload.city.strip(),
        "notes": payload.notes.strip(),
    }


def _vehicle_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "brand": row.get("brand") or "",
        "model": row.get("model") or "",
        "generation": row.get("generation") or "",
        "year": row.get("year") or "",
        "engine": row.get("engine") or "",
        "fuel": row.get("fuel") or row.get("fuel_type") or "",
        "fuel_type": row.get("fuel_type") or row.get("fuel") or "",
        "transmission": row.get("transmission") or "",
        "drive": row.get("drive") or "",
        "vin": row.get("vin") or "",
        "nickname": row.get("nickname") or "",
        "mileage": row.get("mileage") or "",
        "photo_url": row.get("photo_url") or "",
        "country": row.get("country") or "",
        "city": row.get("city") or "",
        "notes": row.get("notes") or "",
        "lifecycle_status": row.get("lifecycle_status") or "ACTIVE",
        "trashed_at": row.get("trashed_at"),
        "restore_until": row.get("restore_until"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _has_vehicle_identity(payload: VehiclePayload) -> bool:
    return bool(payload.brand.strip() and payload.model.strip())


@router.get("")
async def get_vehicles(request: Request, include_trashed: bool = False) -> dict[str, list[dict[str, Any]]]:
    try:
        user = await get_or_create_profile(request=request, require_auth=True)
        return {"vehicles": [_vehicle_response(row) for row in repo.list_user_vehicles(user_id=user.id, include_trashed=include_trashed)]}
    except HTTPException:
        raise
    except (SupabaseUnavailableError, SupabaseOperationError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/{vehicle_id}")
async def get_vehicle(vehicle_id: int, request: Request) -> dict[str, Any]:
    user = await get_or_create_profile(request=request, require_auth=True)
    row = repo.get_vehicle(user_id=user.id, vehicle_id=vehicle_id)
    if not row:
        raise HTTPException(status_code=404, detail="Vehicle not found.")
    return {"vehicle": _vehicle_response(row), "specs": repo.get_vehicle_specs(user_id=user.id, vehicle_id=vehicle_id)}


@router.post("")
async def create_vehicle(payload: VehiclePayload, request: Request) -> dict[str, Any]:
    user = await get_or_create_profile(request=request, payload=payload.model_dump(), require_auth=True)
    if not _has_vehicle_identity(payload):
        raise HTTPException(status_code=400, detail="Vehicle brand and model are required.")
    row = repo.save_vehicle(user_id=user.id, payload=_payload_to_db(payload))
    if not row:
        raise HTTPException(status_code=500, detail="Vehicle was not saved.")
    return {"vehicle": _vehicle_response(row)}


@router.post("/enrich")
async def enrich_vehicle(payload: VehiclePayload) -> dict[str, Any]:
    return {"vehicle": enrich_vehicle_profile(payload.model_dump())}


@router.put("/{vehicle_id}")
async def update_vehicle(vehicle_id: int, payload: VehiclePayload, request: Request) -> dict[str, Any]:
    user = await get_or_create_profile(request=request, payload=payload.model_dump(), require_auth=True)
    row = repo.save_vehicle(user_id=user.id, vehicle_id=vehicle_id, payload=_payload_to_db(payload))
    if not row:
        raise HTTPException(status_code=404, detail="Vehicle not found.")
    return {"vehicle": _vehicle_response(row)}


@router.delete("/{vehicle_id}")
async def remove_vehicle(vehicle_id: int, request: Request) -> dict[str, bool]:
    user = await get_or_create_profile(request=request, require_auth=True)
    deleted = repo.soft_delete_vehicle(user_id=user.id, vehicle_id=vehicle_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Vehicle not found.")
    return {"deleted": True}


@router.post("/{vehicle_id}/restore")
async def restore_vehicle(vehicle_id: int, request: Request) -> dict[str, Any]:
    user = await get_or_create_profile(request=request, require_auth=True)
    row = repo.restore_vehicle(user_id=user.id, vehicle_id=vehicle_id)
    if not row:
        raise HTTPException(status_code=404, detail="Vehicle not found or not restorable.")
    return {"vehicle": _vehicle_response(row)}
