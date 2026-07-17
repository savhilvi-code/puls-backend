from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from app.database.supabase import SupabaseOperationError, SupabaseUnavailableError, find_user_by_fields, get_user_by_id
from app.services.puls_data_service import delete_user_vehicle, list_user_vehicles, save_user_vehicle

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])

VEHICLE_SPEC_NOTE_KEY = "_puls_vehicle_meta"
VEHICLE_SPEC_FIELDS = (
    "displacement",
    "power",
    "torque",
    "engine_type",
    "cylinders",
    "emissions",
    "tank",
)


class VehiclePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    user_id: int | None = None
    auth_user_id: str = ""
    email: str = ""
    brand: str = ""
    model: str = ""
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
    displacement: str = ""
    power: str = ""
    torque: str = ""
    engine_type: str = ""
    cylinders: str = ""
    emissions: str = ""
    tank: str = ""
    country: str = ""
    city: str = ""
    notes: str = ""


def _safe_int(value: int | str | None) -> int | None:
    if value in (None, ""):
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if not digits:
        return None
    return int(digits)


def _resolve_user_id(*, user_id: int | None, auth_user_id: str = "", email: str = "") -> int:
    if user_id:
        user = get_user_by_id(user_id)
        if user and user.id:
            return user.id
    user = find_user_by_fields(auth_user_id=auth_user_id, email=email)
    if user and user.id:
        return user.id
    raise HTTPException(status_code=404, detail="User profile not found.")


def _extract_vehicle_meta(notes: Any) -> tuple[dict[str, Any], str]:
    raw_notes = str(notes or "").strip()
    if not raw_notes:
        return {}, ""
    try:
        parsed = json.loads(raw_notes)
    except Exception:
        return {}, raw_notes
    if not isinstance(parsed, dict):
        return {}, raw_notes
    meta = parsed.get(VEHICLE_SPEC_NOTE_KEY)
    if not isinstance(meta, dict):
        return {}, raw_notes
    manual_note = str(meta.get("manual_note") or "").strip()
    return meta, manual_note


def _pack_vehicle_notes(*, raw_notes: str, payload: VehiclePayload) -> str:
    manual_note = raw_notes.strip()
    meta: dict[str, str] = {}
    for field in VEHICLE_SPEC_FIELDS:
        value = str(getattr(payload, field, "") or "").strip()
        if value:
          meta[field] = value
    if manual_note:
        meta["manual_note"] = manual_note
    if not meta:
        return manual_note
    return json.dumps({VEHICLE_SPEC_NOTE_KEY: meta}, ensure_ascii=False, separators=(",", ":"))


def _vehicle_response(row: dict[str, Any]) -> dict[str, Any]:
    meta, manual_note = _extract_vehicle_meta(row.get("notes"))
    return {
        "id": row.get("id"),
        "user_id": row.get("user_id"),
        "brand": row.get("brand") or "",
        "model": row.get("model") or "",
        "year": row.get("year") or "",
        "engine": row.get("engine") or "",
        "fuel": row.get("fuel") or row.get("fuel_type") or "",
        "fuel_type": row.get("fuel_type") or row.get("fuel") or "",
        "transmission": row.get("transmission") or "",
        "drive": row.get("drive") or row.get("drive_type") or "",
        "vin": row.get("vin") or "",
        "nickname": row.get("nickname") or "",
        "mileage": row.get("mileage") or "",
        "photo_url": row.get("photo_url") or "",
        "displacement": row.get("displacement") or meta.get("displacement") or "",
        "power": row.get("power") or meta.get("power") or "",
        "torque": row.get("torque") or meta.get("torque") or "",
        "engine_type": row.get("engine_type") or meta.get("engine_type") or "",
        "cylinders": row.get("cylinders") or meta.get("cylinders") or "",
        "emissions": row.get("emissions") or meta.get("emissions") or "",
        "tank": row.get("tank") or meta.get("tank") or "",
        "country": row.get("country") or "",
        "city": row.get("city") or "",
        "notes": manual_note,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _payload_to_db(payload: VehiclePayload) -> dict[str, Any]:
    packed_notes = _pack_vehicle_notes(raw_notes=payload.notes, payload=payload)
    data = {
        "brand": payload.brand.strip(),
        "model": payload.model.strip(),
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
        "notes": packed_notes,
    }
    return data


@router.get("")
async def get_vehicles(
    user_id: int | None = Query(default=None),
    auth_user_id: str = Query(default=""),
    email: str = Query(default=""),
) -> dict[str, list[dict[str, Any]]]:
    try:
        resolved_user_id = _resolve_user_id(user_id=user_id, auth_user_id=auth_user_id, email=email)
        return {"vehicles": [_vehicle_response(row) for row in list_user_vehicles(user_id=resolved_user_id)]}
    except HTTPException:
        raise
    except (SupabaseUnavailableError, SupabaseOperationError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("")
async def create_vehicle(payload: VehiclePayload) -> dict[str, Any]:
    try:
        user_id = _resolve_user_id(user_id=payload.user_id, auth_user_id=payload.auth_user_id, email=payload.email)
        row = save_user_vehicle(user_id=user_id, vehicle_id=None, payload=_payload_to_db(payload))
        if not row:
            raise HTTPException(status_code=500, detail="Vehicle was not saved.")
        return {"vehicle": _vehicle_response(row)}
    except HTTPException:
        raise
    except (SupabaseUnavailableError, SupabaseOperationError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.put("/{vehicle_id}")
async def update_vehicle(vehicle_id: int, payload: VehiclePayload) -> dict[str, Any]:
    try:
        user_id = _resolve_user_id(user_id=payload.user_id, auth_user_id=payload.auth_user_id, email=payload.email)
        row = save_user_vehicle(user_id=user_id, vehicle_id=vehicle_id, payload=_payload_to_db(payload))
        if not row:
            raise HTTPException(status_code=404, detail="Vehicle not found.")
        return {"vehicle": _vehicle_response(row)}
    except HTTPException:
        raise
    except (SupabaseUnavailableError, SupabaseOperationError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete("/{vehicle_id}")
async def remove_vehicle(
    vehicle_id: int,
    user_id: int | None = Query(default=None),
    auth_user_id: str = Query(default=""),
    email: str = Query(default=""),
) -> dict[str, bool]:
    try:
        resolved_user_id = _resolve_user_id(user_id=user_id, auth_user_id=auth_user_id, email=email)
        deleted = delete_user_vehicle(user_id=resolved_user_id, vehicle_id=vehicle_id)
        return {"deleted": deleted}
    except HTTPException:
        raise
    except (SupabaseUnavailableError, SupabaseOperationError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
