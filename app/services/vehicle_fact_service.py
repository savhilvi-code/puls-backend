from __future__ import annotations

import re
from dataclasses import dataclass
import logging
from typing import Any

from app.services import v2_repository as repo


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VehicleSpecFact:
    parameter_key: str
    parameter_name: str
    category: str
    value: str
    value_kind: str
    source_type: str
    confirmed_replacement: bool = False


_CHANGE_MARKERS = (
    "исправь", "измени", "замени", "укажи", "поставь", "запиши",
    "correct", "change", "replace", "set", "update",
)
_ACTUAL_MARKERS = (
    "у меня стоит", "у меня стоят", "установлен", "установлены", "поставил",
    "поставлены", "залито", "использую", "лью", "фактически",
    "installed", "fitted", "i use", "filled with", "actually uses",
)
_RECOMMENDED_MARKERS = (
    "рекомендуется", "рекомендовано", "по мануалу", "по руководству", "по каталогу",
    "manufacturer specifies", "manual specifies", "recommended", "catalog lists",
)


def extract_vehicle_correction(text: str) -> dict[str, str] | None:
    lowered = " ".join(str(text or "").lower().split())
    if not any(marker in lowered for marker in _CHANGE_MARKERS):
        return None
    if any(marker in lowered for marker in ("акпп", "автомат", "automatic", "al4")):
        return {"transmission": "Automatic"}
    if any(marker in lowered for marker in ("мкпп", "механик", "manual")):
        return {"transmission": "Manual"}
    return None


def _source_type(lowered: str) -> str:
    if "мануал" in lowered or "руководств" in lowered or "manual" in lowered:
        return "MANUAL"
    if "каталог" in lowered or "catalog" in lowered:
        return "CATALOG"
    return "PULS"


def _part_value(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.IGNORECASE)
    return " ".join(match.group(1).strip(" .,:;").split()) if match else ""


def extract_vehicle_spec_fact(text: str) -> VehicleSpecFact | None:
    source = " ".join(str(text or "").strip().split())
    lowered = source.lower()
    actual = any(marker in lowered for marker in _ACTUAL_MARKERS)
    recommended = any(marker in lowered for marker in _RECOMMENDED_MARKERS)
    if not actual and not recommended:
        return None

    kind = "actual" if actual else "recommended"
    source_type = "USER" if actual else _source_type(lowered)
    confirmed_replacement = actual and any(marker in lowered for marker in _CHANGE_MARKERS)

    viscosity = re.search(r"\b(\d{1,2}\s*[wW]\s*[- ]?\s*\d{2})\b", source)
    if viscosity and any(word in lowered for word in ("масл", "oil")):
        value = re.sub(r"\s+", "", viscosity.group(1)).upper()
        return VehicleSpecFact("engine_oil_viscosity", "Engine oil viscosity", "fluids", value, kind, source_type, confirmed_replacement)

    tire = re.search(r"\b(\d{3}/\d{2}\s*[rR]\s*\d{2})\b", source)
    if tire:
        value = re.sub(r"\s+", "", tire.group(1)).upper()
        return VehicleSpecFact("tire_size", "Tire size", "wheels", value, kind, source_type, confirmed_replacement)

    plugs = _part_value(
        source,
        r"(?:свеч(?:и|а|ей|у)?(?:\s+зажигания)?|spark\s+plugs?)\s+(?:модели\s+)?([A-Za-z0-9][A-Za-z0-9._/-]*(?:\s+[A-Za-z0-9][A-Za-z0-9._/-]*){0,2})",
    )
    if plugs:
        return VehicleSpecFact("spark_plugs", "Spark plugs", "ignition", plugs, kind, source_type, confirmed_replacement)

    atf = _part_value(
        source,
        r"(?:atf|трансмиссионн\w*\s+жидкост\w*|масл\w*\s+(?:в|для)\s+акпп)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9 ._/-]{1,30})",
    )
    if atf:
        return VehicleSpecFact("transmission_fluid", "Transmission fluid", "fluids", atf, kind, source_type, confirmed_replacement)

    brake_fluid = re.search(r"\b(DOT\s*(?:3|4|5(?:\.1)?))\b", source, re.IGNORECASE)
    if brake_fluid:
        return VehicleSpecFact("brake_fluid", "Brake fluid", "fluids", brake_fluid.group(1).upper().replace(" ", ""), kind, source_type, confirmed_replacement)

    pressure = re.search(r"\b(\d(?:[.,]\d{1,2})?\s*(?:bar|psi|бар))\b", source, re.IGNORECASE)
    if pressure and any(word in lowered for word in ("шин", "колес", "tire", "tyre")):
        return VehicleSpecFact("tire_pressure", "Tire pressure", "wheels", pressure.group(1), kind, source_type, confirmed_replacement)

    capacity = re.search(r"\b(\d(?:[.,]\d{1,2})?\s*(?:л|l|liter|litre))\b", source, re.IGNORECASE)
    if capacity and any(word in lowered for word in ("масл", "oil")):
        return VehicleSpecFact("engine_oil_capacity", "Engine oil capacity", "fluids", capacity.group(1), kind, source_type, confirmed_replacement)

    for key, name, category, pattern in (
        ("oil_filter", "Oil filter", "filters", r"(?:маслян\w*\s+фильтр\w*|oil\s+filter)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9._/-]{2,30})"),
        ("air_filter", "Air filter", "filters", r"(?:воздушн\w*\s+фильтр\w*|air\s+filter)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9._/-]{2,30})"),
        ("cabin_filter", "Cabin filter", "filters", r"(?:салонн\w*\s+фильтр\w*|cabin\s+filter)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9._/-]{2,30})"),
        ("fuel_filter", "Fuel filter", "filters", r"(?:топливн\w*\s+фильтр\w*|fuel\s+filter)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9._/-]{2,30})"),
        ("bulbs", "Bulbs", "electrical", r"(?:ламп\w*|bulbs?)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9._/-]{1,20})"),
        ("coolant", "Coolant", "fluids", r"(?:антифриз\w*|охлаждающ\w*\s+жидкост\w*|coolant)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9 ._/-]{1,30})"),
        ("wiper_sizes", "Wiper sizes", "body", r"(?:дворник\w*|щетк\w*\s+стеклоочистител\w*|wipers?)\D{0,12}(\d{2,3}\s*(?:/|и|and|x)\s*\d{2,3}\s*(?:mm|мм|inch|дюйм\w*)?)"),
    ):
        value = _part_value(source, pattern)
        if value:
            return VehicleSpecFact(key, name, category, value, kind, source_type, confirmed_replacement)

    return None


def persist_vehicle_spec_fact(
    *, user_id: str | None, vehicle_id: str | None, fact: VehicleSpecFact,
) -> dict[str, Any]:
    specs = repo.get_vehicle_specs(user_id=user_id, vehicle_id=vehicle_id) or {}
    existing = next(
        (
            item for item in specs.get("items", [])
            if str(item.get("parameter_key") or "") == fact.parameter_key
        ),
        None,
    )

    if fact.value_kind == "actual" and existing:
        current = str(existing.get("actual_value") or "").strip()
        user_owned = str(existing.get("source_type") or "").upper() == "USER"
        if current and user_owned and current.casefold() != fact.value.casefold() and not fact.confirmed_replacement:
            return {"status": "conflict", "existing": current, "requested": fact.value}

    value_field = "actual_value" if fact.value_kind == "actual" else "recommended_value"
    payload = {
        "category": fact.category,
        "parameter_key": fact.parameter_key,
        "parameter_name": fact.parameter_name,
        value_field: fact.value,
    }
    if fact.value_kind == "actual":
        payload["source_type"] = "USER"
        payload["metadata"] = {
            **((existing or {}).get("metadata") or {}),
            "actual_value_origin": "USER_CONFIRMED",
        }
    elif existing and str(existing.get("actual_value") or "").strip() and str(existing.get("source_type") or "").upper() == "USER":
        payload["metadata"] = {
            **(existing.get("metadata") or {}),
            "recommended_source_type": fact.source_type,
        }
    else:
        payload["source_type"] = fact.source_type
        payload["metadata"] = {"recommended_source_type": fact.source_type}
    saved = repo.upsert_vehicle_specs(user_id=user_id, vehicle_id=vehicle_id, payload=payload)
    if not saved:
        return {"status": "failed", "saved": saved}

    fresh_specs = repo.get_vehicle_specs(user_id=user_id, vehicle_id=vehicle_id) or {}
    persisted = next(
        (
            item for item in fresh_specs.get("items", [])
            if str(item.get("parameter_key") or "") == fact.parameter_key
        ),
        None,
    )
    actual = str((persisted or {}).get(value_field) or "").strip()
    if actual.casefold() != str(fact.value).strip().casefold():
        logger.warning(
            "Vehicle spec write verification failed user_id=%s vehicle_id=%s parameter_key=%s",
            user_id, vehicle_id, fact.parameter_key,
        )
        return {"status": "failed", "saved": saved}
    return {"status": "saved", "saved": persisted}


def persist_vehicle_correction(
    *, user_id: str | None, vehicle_id: str | None, values: dict[str, Any],
) -> dict[str, Any]:
    """Write canonical vehicle fields and prove the result with an owned fresh read."""
    aliases = {
        "brand": "make",
        "engine": "engine_code",
        "fuel": "fuel_type",
        "drive": "drivetrain",
    }
    canonical = {
        aliases.get(str(key), str(key)): value
        for key, value in (values or {}).items()
    }
    saved = repo.save_vehicle(user_id=user_id, vehicle_id=vehicle_id, payload=canonical)
    if not saved:
        return {"status": "failed"}
    fresh = repo.get_vehicle(user_id=user_id, vehicle_id=vehicle_id)
    verified = bool(fresh) and all(
        str(fresh.get(key) or "").strip().casefold()
        == str(value or "").strip().casefold()
        for key, value in canonical.items()
    )
    if not verified:
        logger.warning(
            "Vehicle write verification failed user_id=%s vehicle_id=%s fields=%s",
            user_id, vehicle_id, sorted(canonical),
        )
        return {"status": "failed"}
    return {"status": "saved", "vehicle": fresh}
