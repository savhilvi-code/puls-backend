from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from app.database.supabase import SupabaseOperationError, SupabaseUnavailableError, find_user_by_fields, get_user_by_id
from app.services.puls_data_service import delete_user_vehicle, list_user_vehicles, save_user_vehicle
from app.services.vehicle_enrichment_service import decode_vehicle_profile, enrich_vehicle_profile

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
VEHICLE_PRIMARY_IDENTITY_FIELDS = ("brand", "model", "year", "engine")


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


def _clean_text(value: Any, *, upper: bool = False) -> str:
    text = str(value or "").strip()
    return text.upper() if upper else text


def _payload_has_meaningful_vehicle_data(payload: VehiclePayload) -> bool:
    return any(
        _clean_text(getattr(payload, field, ""))
        for field in (
            "brand",
            "model",
            "year",
            "engine",
            "fuel",
            "fuel_type",
            "transmission",
            "drive",
            "vin",
            "nickname",
            "mileage",
            "photo_url",
            *VEHICLE_SPEC_FIELDS,
        )
    )


def _find_duplicate_vehicle_row(*, user_id: int, payload: VehiclePayload) -> dict[str, Any] | None:
    rows = list_user_vehicles(user_id=user_id)
    if not rows:
        return None

    incoming_vin = _clean_text(payload.vin, upper=True)
    if incoming_vin:
        for row in rows:
            if _clean_text(row.get("vin"), upper=True) == incoming_vin:
                return row

    brand = _clean_text(payload.brand).casefold()
    model = _clean_text(payload.model).casefold()
    year = _safe_int(payload.year)
    engine = _clean_text(payload.engine).casefold()
    if not (brand and model and (year or engine)):
        return None

    for row in rows:
        row_brand = _clean_text(row.get("brand")).casefold()
        row_model = _clean_text(row.get("model")).casefold()
        row_year = _safe_int(row.get("year"))
        row_engine = _clean_text(row.get("engine")).casefold()
        if row_brand != brand or row_model != model:
            continue
        if year and row_year != year:
            continue
        if engine and row_engine != engine:
            continue
        return row
    return None


def _merge_vehicle_db_payload(existing_row: dict[str, Any], incoming_payload: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key, value in incoming_payload.items():
        if key in {"user_id", "updated_at"}:
            merged[key] = value
            continue
        if value in (None, ""):
            merged[key] = existing_row.get(key)
        else:
            merged[key] = value
    return merged


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


def _draft_vehicle_response(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": data.get("id") or "",
        "brand": data.get("brand") or "",
        "model": data.get("model") or "",
        "year": data.get("year") or "",
        "engine": data.get("engine") or "",
        "fuel": data.get("fuel") or data.get("fuel_type") or "",
        "fuel_type": data.get("fuel_type") or data.get("fuel") or "",
        "transmission": data.get("transmission") or "",
        "drive": data.get("drive") or "",
        "vin": data.get("vin") or "",
        "nickname": data.get("nickname") or "",
        "mileage": data.get("mileage") or "",
        "photo_url": data.get("photo_url") or "",
        "displacement": data.get("displacement") or "",
        "power": data.get("power") or "",
        "torque": data.get("torque") or "",
        "engine_type": data.get("engine_type") or "",
        "cylinders": data.get("cylinders") or "",
        "emissions": data.get("emissions") or "",
        "tank": data.get("tank") or "",
        "country": data.get("country") or "",
        "city": data.get("city") or "",
        "notes": data.get("notes") or "",
    }


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
        if not _payload_has_meaningful_vehicle_data(payload):
            raise HTTPException(status_code=400, detail="Vehicle payload is empty.")
        db_payload = _payload_to_db(payload)
        duplicate_row = _find_duplicate_vehicle_row(user_id=user_id, payload=payload)
        effective_vehicle_id = int(duplicate_row["id"]) if duplicate_row and duplicate_row.get("id") else None
        effective_payload = _merge_vehicle_db_payload(duplicate_row, db_payload) if duplicate_row else db_payload
        row = save_user_vehicle(user_id=user_id, vehicle_id=effective_vehicle_id, payload=effective_payload)
        if not row:
            raise HTTPException(status_code=500, detail="Vehicle was not saved.")
        return {"vehicle": _vehicle_response(row)}
    except HTTPException:
        raise
    except (SupabaseUnavailableError, SupabaseOperationError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/enrich")
async def enrich_vehicle(payload: VehiclePayload) -> dict[str, Any]:
    try:
        enriched = enrich_vehicle_profile(payload.model_dump())
        return {"vehicle": _draft_vehicle_response(enriched)}
    except HTTPException:
        raise
    except (SupabaseUnavailableError, SupabaseOperationError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/decode")
async def decode_vehicle(payload: VehiclePayload) -> dict[str, Any]:
    try:
        decoded = decode_vehicle_profile(payload.model_dump())
        return {"vehicle": _draft_vehicle_response(decoded)}
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
