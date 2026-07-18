from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from typing import Any

from app.services.openai_service import OpenAIRouterUnavailableError, get_openai_client, is_configured

CURRENT_YEAR_MAX = 2027
WIKIPEDIA_API_HEADERS = {"User-Agent": "PULS-CarDiagnostic/1.0"}
JSON_API_HEADERS = {"User-Agent": "PULS-CarDiagnostic/1.0", "Accept": "application/json"}
FULL_VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$", re.IGNORECASE)
JDM_CHASSIS_PATTERN = re.compile(r"^[A-Z0-9-]{8,18}$", re.IGNORECASE)
JDM_CHASSIS_COMPACT_PATTERN = re.compile(r"^(?:[A-Z]{2,5}\d{5,10}|[A-Z]{2,5}\d{2,7}[A-Z]?\d{4,8})$", re.IGNORECASE)
JDM_CHASSIS_PARTS_PATTERN = re.compile(r"^([A-Z]{1,5}\d{2,3}[A-Z]?)-?(\d{4,8})$", re.IGNORECASE)
VINDECODER_API_BASE_URL = os.getenv("VINDECODER_API_BASE_URL", "https://bp.autoiso.pl/api/v3").rstrip("/")
VINDECODER_API_UID = os.getenv("VINDECODER_API_UID", "").strip()
VINDECODER_API_KEY = os.getenv("VINDECODER_API_KEY", "").strip()
KNOWN_JDM_CHASSIS_PROFILES: dict[str, dict[str, str]] = {
    "PNT30": {
        "brand": "Nissan",
        "model": "X-Trail GT",
        "year": "",
        "engine": "SR20VET",
        "fuel": "Gasoline",
        "fuel_type": "Gasoline",
        "transmission": "4-speed automatic",
        "drive": "4WD",
        "displacement": "2.0L",
        "power": "280 PS",
        "torque": "309 Nm",
        "engine_type": "Turbocharged inline-4",
        "cylinders": "4",
        "emissions": "",
        "tank": "",
        "photo_query": "Nissan X-Trail GT PNT30",
        "wikipedia_title": "Nissan X-Trail",
    },
    "NT30": {
        "brand": "Nissan",
        "model": "X-Trail",
        "year": "",
        "engine": "",
        "fuel": "",
        "fuel_type": "",
        "transmission": "",
        "drive": "4WD",
        "displacement": "",
        "power": "",
        "torque": "",
        "engine_type": "",
        "cylinders": "",
        "emissions": "",
        "tank": "",
        "photo_query": "Nissan X-Trail NT30",
        "wikipedia_title": "Nissan X-Trail",
    },
    "T30": {
        "brand": "Nissan",
        "model": "X-Trail",
        "year": "",
        "engine": "",
        "fuel": "",
        "fuel_type": "",
        "transmission": "",
        "drive": "",
        "displacement": "",
        "power": "",
        "torque": "",
        "engine_type": "",
        "cylinders": "",
        "emissions": "",
        "tank": "",
        "photo_query": "Nissan X-Trail T30",
        "wikipedia_title": "Nissan X-Trail",
    },
}

VEHICLE_ENRICHMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "brand": {"type": "string"},
        "model": {"type": "string"},
        "year": {"type": "string"},
        "engine": {"type": "string"},
        "fuel": {"type": "string"},
        "drive": {"type": "string"},
        "transmission": {"type": "string"},
        "displacement": {"type": "string"},
        "power": {"type": "string"},
        "torque": {"type": "string"},
        "engine_type": {"type": "string"},
        "cylinders": {"type": "string"},
        "emissions": {"type": "string"},
        "tank": {"type": "string"},
        "photo_query": {"type": "string"},
        "wikipedia_title": {"type": "string"},
    },
    "required": [
        "brand",
        "model",
        "year",
        "engine",
        "fuel",
        "drive",
        "transmission",
        "displacement",
        "power",
        "torque",
        "engine_type",
        "cylinders",
        "emissions",
        "tank",
        "photo_query",
        "wikipedia_title",
    ],
    "additionalProperties": False,
}

ENRICHMENT_PROMPT = """You are PULS vehicle profile enricher.
Use web search to verify vehicle facts.

Rules:
- Prefer exact VIN-based data when VIN is present.
- If the identifier is a Japanese chassis/frame number rather than a 17-character VIN, use it to identify the exact car generation and stock engine where possible.
- If a chassis code candidate is provided, match that exact code. Do not add or remove digits from it. For example, `PNT30` is not `PNT3000`.
- If a field is uncertain, return an empty string instead of guessing.
- Keep existing user-provided values unless web evidence strongly supports a better value.
- Never return a year earlier than 1981 or later than 2027. If uncertain, return empty year.
- For power, torque, displacement, cylinders, transmission, drive and fuel, prefer factory stock values.
- `photo_query` should be a short query suitable for finding a representative vehicle photo.
- `wikipedia_title` should be the most likely English Wikipedia vehicle title with an image, or empty if unsure.
- Return only JSON that matches the schema.
"""


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _extract_json(text: str) -> dict[str, Any]:
    candidate = _clean_text(text)
    match = re.search(r"\{[\s\S]*\}", candidate)
    if match:
        candidate = match.group(0)
    data = json.loads(candidate)
    if not isinstance(data, dict):
        raise ValueError("Vehicle enrichment response is not a JSON object.")
    return data


def _normalize_year(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if not digits:
        return ""
    year = int(digits[:4])
    if year < 1981 or year > CURRENT_YEAR_MAX:
        return ""
    return str(year)


def _normalize_vehicle_payload(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "id": _clean_text(payload.get("id")),
        "brand": _clean_text(payload.get("brand")),
        "model": _clean_text(payload.get("model")),
        "year": _normalize_year(payload.get("year")),
        "engine": _clean_text(payload.get("engine")),
        "fuel": _clean_text(payload.get("fuel") or payload.get("fuel_type")),
        "fuel_type": _clean_text(payload.get("fuel_type") or payload.get("fuel")),
        "transmission": _clean_text(payload.get("transmission")),
        "drive": _clean_text(payload.get("drive")),
        "vin": _clean_text(payload.get("vin")).upper(),
        "nickname": _clean_text(payload.get("nickname")),
        "mileage": _clean_text(payload.get("mileage")),
        "photo_url": _clean_text(payload.get("photo_url")),
        "displacement": _clean_text(payload.get("displacement")),
        "power": _clean_text(payload.get("power")),
        "torque": _clean_text(payload.get("torque")),
        "engine_type": _clean_text(payload.get("engine_type")),
        "cylinders": _clean_text(payload.get("cylinders")),
        "emissions": _clean_text(payload.get("emissions")),
        "tank": _clean_text(payload.get("tank")),
        "country": _clean_text(payload.get("country")),
        "city": _clean_text(payload.get("city")),
        "notes": _clean_text(payload.get("notes")),
    }


def _classify_vehicle_identifier(value: str) -> str:
    normalized = _clean_text(value).upper()
    if not normalized:
        return ""
    if FULL_VIN_PATTERN.fullmatch(normalized):
        return "vin"
    if (
        JDM_CHASSIS_PATTERN.fullmatch(normalized)
        and ("-" in normalized or JDM_CHASSIS_COMPACT_PATTERN.fullmatch(normalized))
    ):
        return "jdm_chassis"
    return "generic"


def _extract_jdm_chassis_parts(value: str) -> tuple[str, str]:
    normalized = _clean_text(value).upper()
    compact = normalized.replace("-", "")
    match = JDM_CHASSIS_PARTS_PATTERN.fullmatch(normalized) or JDM_CHASSIS_PARTS_PATTERN.fullmatch(compact)
    if not match:
        return "", ""
    return str(match.group(1) or "").upper(), str(match.group(2) or "").upper()


def _build_enrichment_input(vehicle: dict[str, str]) -> str:
    identifier = vehicle["vin"]
    identifier_type = _classify_vehicle_identifier(identifier)
    chassis_code, chassis_serial = _extract_jdm_chassis_parts(identifier)
    if identifier_type == "vin":
        identifier_block = f"VIN: {identifier}\n"
    elif identifier_type == "jdm_chassis":
        identifier_block = (
            f"Japanese chassis/frame number: {identifier}\n"
            f"Chassis code candidate: {chassis_code}\n"
            f"Serial candidate: {chassis_serial}\n"
        )
    elif identifier:
        identifier_block = f"Vehicle identifier: {identifier}\n"
    else:
        identifier_block = "Vehicle identifier: \n"

    return (
        "Enrich this car draft.\n"
        f"Identifier type: {identifier_type or 'unknown'}\n"
        f"Brand: {vehicle['brand']}\n"
        f"Model: {vehicle['model']}\n"
        f"Year: {vehicle['year']}\n"
        f"Engine: {vehicle['engine']}\n"
        f"Fuel: {vehicle['fuel']}\n"
        f"Drive: {vehicle['drive']}\n"
        f"Transmission: {vehicle['transmission']}\n"
        + identifier_block
        + f"Current displacement: {vehicle['displacement']}\n"
        f"Current power: {vehicle['power']}\n"
        f"Current torque: {vehicle['torque']}\n"
        f"Current engine type: {vehicle['engine_type']}\n"
        f"Current cylinders: {vehicle['cylinders']}\n"
        f"Current emissions: {vehicle['emissions']}\n"
        f"Current tank: {vehicle['tank']}\n"
    )


def _search_wikipedia_summary_image(title: str) -> str:
    clean_title = _clean_text(title)
    if not clean_title:
        return ""
    url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(clean_title.replace(" ", "_"))
    request = urllib.request.Request(url, headers=WIKIPEDIA_API_HEADERS)
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))
    original = payload.get("originalimage") or {}
    thumbnail = payload.get("thumbnail") or {}
    return _clean_text(original.get("source") or thumbnail.get("source"))


def _search_commons_image(query: str) -> str:
    clean_query = _clean_text(query)
    if not clean_query:
        return ""
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "generator": "search",
            "gsrsearch": clean_query,
            "gsrnamespace": "6",
            "prop": "imageinfo",
            "iiprop": "url",
            "iiurlwidth": "1400",
            "format": "json",
        }
    )
    url = f"https://commons.wikimedia.org/w/api.php?{params}"
    request = urllib.request.Request(url, headers=WIKIPEDIA_API_HEADERS)
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))
    pages = (payload.get("query") or {}).get("pages") or {}
    for page in pages.values():
        image_info = page.get("imageinfo") or []
        if not image_info:
            continue
        candidate = image_info[0]
        found_url = _clean_text(candidate.get("thumburl") or candidate.get("url"))
        if found_url:
            return found_url
    return ""


def _find_vehicle_photo(vehicle: dict[str, str], enrichment: dict[str, str]) -> str:
    if vehicle.get("photo_url"):
        return vehicle["photo_url"]

    candidates = [
        enrichment.get("wikipedia_title", ""),
        enrichment.get("photo_query", ""),
        " ".join(part for part in (vehicle.get("brand", ""), vehicle.get("model", ""), vehicle.get("year", "")) if part).strip(),
        " ".join(part for part in (vehicle.get("brand", ""), vehicle.get("model", "")) if part).strip(),
    ]

    for title in candidates:
        try:
            image_url = _search_wikipedia_summary_image(title)
        except Exception:
            image_url = ""
        if image_url:
            return image_url

    for query in candidates:
        try:
            image_url = _search_commons_image(query)
        except Exception:
            image_url = ""
        if image_url:
            return image_url
    return ""


def _extract_provider_value(container: dict[str, Any], key: str) -> str:
    entry = container.get(key)
    if isinstance(entry, dict):
        return _clean_text(entry.get("value"))
    return _clean_text(entry)


def _fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=JSON_API_HEADERS)
    with urllib.request.urlopen(request, timeout=18) as response:
        return json.loads(response.read().decode("utf-8"))


def _decode_with_vindecoder(vin: str) -> dict[str, str]:
    if not (VINDECODER_API_UID and VINDECODER_API_KEY):
        return {}

    checksum = hashlib.md5(f"{VINDECODER_API_UID}{VINDECODER_API_KEY}{vin}".encode("utf-8")).hexdigest()
    url = (
        f"{VINDECODER_API_BASE_URL}/getDecoderFree/"
        f"apiuid:{urllib.parse.quote(VINDECODER_API_UID)}/"
        f"checksum:{checksum}/"
        f"vin:{urllib.parse.quote(vin)}/"
        "lang:en"
    )
    payload = _fetch_json(url)
    decoder = payload.get("decoder") or {}
    return {
        "brand": _extract_provider_value(decoder, "make"),
        "model": _extract_provider_value(decoder, "model"),
        "year": _normalize_year(_extract_provider_value(decoder, "model_year")),
        "engine": (
            _extract_provider_value(decoder, "engine_code")
            or _extract_provider_value(decoder, "engine")
            or _extract_provider_value(decoder, "engine_model")
        ),
        "fuel": _extract_provider_value(decoder, "fuel_type"),
        "fuel_type": _extract_provider_value(decoder, "fuel_type"),
        "transmission": (
            _extract_provider_value(decoder, "transmission")
            or _extract_provider_value(decoder, "gearbox")
        ),
        "drive": (
            _extract_provider_value(decoder, "drive_type")
            or _extract_provider_value(decoder, "driven_axle")
        ),
        "displacement": (
            _extract_provider_value(decoder, "engine_displ_l")
            or _extract_provider_value(decoder, "engine_displ_cm3")
        ),
        "power": (
            _extract_provider_value(decoder, "engine_power_hp")
            or _extract_provider_value(decoder, "engine_power_kw")
        ),
        "torque": _extract_provider_value(decoder, "engine_torque_nm"),
        "engine_type": (
            _extract_provider_value(decoder, "engine_type")
            or _extract_provider_value(decoder, "body")
        ),
        "cylinders": _extract_provider_value(decoder, "engine_cylinders"),
        "emissions": _extract_provider_value(decoder, "emission_standard"),
        "tank": _extract_provider_value(decoder, "fuel_tank_capacity"),
        "photo_query": " ".join(
            part
            for part in (
                _extract_provider_value(decoder, "make"),
                _extract_provider_value(decoder, "model"),
                _extract_provider_value(decoder, "model_year"),
            )
            if part
        ).strip(),
        "wikipedia_title": "",
    }


def _decode_with_nhtsa(vin: str) -> dict[str, str]:
    url = (
        "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValuesExtended/"
        f"{urllib.parse.quote(vin)}?format=json"
    )
    payload = _fetch_json(url)
    results = payload.get("Results") or []
    if not isinstance(results, list) or not results:
        return {}
    record = results[0] or {}
    if not isinstance(record, dict):
        return {}
    return {
        "brand": _clean_text(record.get("Make") or record.get("Manufacturer") or record.get("ManufacturerName")),
        "model": _clean_text(record.get("Model") or record.get("Series") or record.get("Trim")),
        "year": _normalize_year(record.get("ModelYear")),
        "engine": "",
        "fuel": "",
        "fuel_type": "",
        "transmission": "",
        "drive": "",
        "displacement": "",
        "power": "",
        "torque": "",
        "engine_type": "",
        "cylinders": "",
        "emissions": "",
        "tank": "",
        "photo_query": " ".join(
            part for part in (
                _clean_text(record.get("Make") or record.get("ManufacturerName")),
                _clean_text(record.get("Model") or record.get("Series") or record.get("Trim")),
                _normalize_year(record.get("ModelYear")),
            ) if part
        ).strip(),
        "wikipedia_title": "",
    }


def _run_model_enrichment(vehicle: dict[str, str]) -> dict[str, str]:
    if not is_configured():
        return {}

    client = get_openai_client()
    response = client.responses.create(
        model="gpt-4.1-mini",
        instructions=ENRICHMENT_PROMPT,
        input=_build_enrichment_input(vehicle),
        max_output_tokens=2200,
        tools=[{"type": "web_search_preview", "search_context_size": "medium"}],
        text={
            "format": {
                "type": "json_schema",
                "name": "vehicle_enrichment",
                "description": "PULS vehicle enrichment output.",
                "schema": VEHICLE_ENRICHMENT_SCHEMA,
                "strict": True,
            }
        },
    )
    raw_text = getattr(response, "output_text", "") or ""
    data = _extract_json(raw_text)
    return {
        "brand": _clean_text(data.get("brand")),
        "model": _clean_text(data.get("model")),
        "year": _normalize_year(data.get("year")),
        "engine": _clean_text(data.get("engine")),
        "fuel": _clean_text(data.get("fuel")),
        "fuel_type": _clean_text(data.get("fuel")),
        "transmission": _clean_text(data.get("transmission")),
        "drive": _clean_text(data.get("drive")),
        "displacement": _clean_text(data.get("displacement")),
        "power": _clean_text(data.get("power")),
        "torque": _clean_text(data.get("torque")),
        "engine_type": _clean_text(data.get("engine_type")),
        "cylinders": _clean_text(data.get("cylinders")),
        "emissions": _clean_text(data.get("emissions")),
        "tank": _clean_text(data.get("tank")),
        "photo_query": _clean_text(data.get("photo_query")),
        "wikipedia_title": _clean_text(data.get("wikipedia_title")),
    }


def _known_jdm_chassis_profile(chassis_code: str) -> dict[str, str]:
    return dict(KNOWN_JDM_CHASSIS_PROFILES.get(_clean_text(chassis_code).upper(), {}))


def decode_vehicle_profile(payload: dict[str, Any]) -> dict[str, str]:
    vehicle = _normalize_vehicle_payload(payload)
    identifier = vehicle.get("vin", "")
    identifier_type = _classify_vehicle_identifier(identifier)
    chassis_code, _ = _extract_jdm_chassis_parts(identifier)

    decoded: dict[str, str] = {}
    if identifier_type == "vin":
        try:
            decoded = _decode_with_vindecoder(identifier)
        except Exception:
            decoded = {}
        if not decoded.get("brand") or not decoded.get("model"):
            try:
                decoded = _decode_with_nhtsa(identifier)
            except Exception:
                decoded = decoded or {}
    elif identifier_type == "jdm_chassis":
        decoded = _known_jdm_chassis_profile(chassis_code)

    merged = dict(vehicle)
    for key in (
        "brand",
        "model",
        "year",
        "engine",
        "fuel",
        "fuel_type",
        "transmission",
        "drive",
        "displacement",
        "power",
        "torque",
        "engine_type",
        "cylinders",
        "emissions",
        "tank",
    ):
        incoming = _clean_text(decoded.get(key))
        if incoming:
            merged[key] = incoming

    if decoded:
        merged["photo_url"] = _find_vehicle_photo(merged, decoded)
    return merged


def enrich_vehicle_profile(payload: dict[str, Any]) -> dict[str, str]:
    vehicle = _normalize_vehicle_payload(payload)
    identifier_type = _classify_vehicle_identifier(vehicle.get("vin", ""))
    chassis_code, _ = _extract_jdm_chassis_parts(vehicle.get("vin", ""))

    known_profile = _known_jdm_chassis_profile(chassis_code)
    if identifier_type == "jdm_chassis" and known_profile:
        merged = dict(vehicle)
        for key, value in known_profile.items():
            if value:
                merged[key] = value
        merged["photo_url"] = _find_vehicle_photo(merged, known_profile)
        return merged

    try:
        enrichment = _run_model_enrichment(vehicle)
    except OpenAIRouterUnavailableError:
        enrichment = {}
    except Exception:
        enrichment = {}

    merged = dict(vehicle)
    for key in (
        "brand",
        "model",
        "year",
        "engine",
        "fuel",
        "fuel_type",
        "transmission",
        "drive",
        "displacement",
        "power",
        "torque",
        "engine_type",
        "cylinders",
        "emissions",
        "tank",
    ):
        incoming = _clean_text(enrichment.get(key))
        if incoming:
            merged[key] = incoming

    if identifier_type == "jdm_chassis" and chassis_code in {"T30", "NT30", "PNT30"}:
        merged["brand"] = "Nissan"
        merged["model"] = "X-Trail"
        if str(merged.get("year") or "").isdigit() and int(str(merged["year"])) < 2000:
            merged["year"] = ""
        if str(merged.get("engine") or "").upper() == "VG30DE":
            merged["engine"] = ""
        if str(merged.get("drive") or "").upper() == "RWD":
            merged["drive"] = ""
        if "3000" in str(merged.get("photo_url") or "") or "300zx" in str(merged.get("photo_url") or "").lower():
            merged["photo_url"] = ""

    merged["photo_url"] = _find_vehicle_photo(merged, enrichment)
    return merged
