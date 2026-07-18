from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any

from app.services.openai_service import OpenAIRouterUnavailableError, get_openai_client, is_configured

CURRENT_YEAR_MAX = 2027
WIKIPEDIA_API_HEADERS = {"User-Agent": "PULS-CarDiagnostic/1.0"}
FULL_VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$", re.IGNORECASE)
JDM_CHASSIS_PATTERN = re.compile(r"^[A-Z0-9-]{8,18}$", re.IGNORECASE)

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
    if "-" in normalized and JDM_CHASSIS_PATTERN.fullmatch(normalized):
        return "jdm_chassis"
    return "generic"


def _build_enrichment_input(vehicle: dict[str, str]) -> str:
    identifier = vehicle["vin"]
    identifier_type = _classify_vehicle_identifier(identifier)
    if identifier_type == "vin":
        identifier_block = f"VIN: {identifier}\n"
    elif identifier_type == "jdm_chassis":
        identifier_block = f"Japanese chassis/frame number: {identifier}\n"
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


def enrich_vehicle_profile(payload: dict[str, Any]) -> dict[str, str]:
    vehicle = _normalize_vehicle_payload(payload)

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

    merged["photo_url"] = _find_vehicle_photo(merged, enrichment)
    return merged
