from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.database.supabase import SupabaseOperationError, SupabaseUnavailableError, get_supabase_client, is_supabase_configured
from app.services.openai_service import OpenAIRouterUnavailableError, get_openai_client, is_configured

CURRENT_YEAR_MAX = 2027
FULL_VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$", re.IGNORECASE)
INNER_SPACES_PATTERN = re.compile(r"\s+")
JDM_CHASSIS_WITH_HYPHEN_PATTERN = re.compile(r"^([A-Z0-9]{2,8})-(\d{4,8})$", re.IGNORECASE)
JDM_CHASSIS_COMPACT_PATTERN = re.compile(r"^([A-Z]{2,7}\d{1,3}[A-Z]?)(\d{4,8})$", re.IGNORECASE)
VALID_IDENTIFIER_CHARS_PATTERN = re.compile(r"^[A-Z0-9-]+$", re.IGNORECASE)
VEHICLE_LOOKUP_SCHEMA = {
    "type": "object",
    "properties": {
        "brand": {"type": "string"},
        "market": {"type": "string"},
        "possible_models": {"type": "array", "items": {"type": "string"}},
        "possible_engines": {"type": "array", "items": {"type": "string"}},
        "year_range": {"type": "string"},
        "sources_confirmed": {"type": "integer"},
        "notes": {"type": "string"},
    },
    "required": [
        "brand",
        "market",
        "possible_models",
        "possible_engines",
        "year_range",
        "sources_confirmed",
        "notes",
    ],
    "additionalProperties": False,
}

YEAR_CODE_MAP = {
    "A": 1980, "B": 1981, "C": 1982, "D": 1983, "E": 1984, "F": 1985, "G": 1986, "H": 1987,
    "J": 1988, "K": 1989, "L": 1990, "M": 1991, "N": 1992, "P": 1993, "R": 1994, "S": 1995,
    "T": 1996, "V": 1997, "W": 1998, "X": 1999, "Y": 2000, "1": 2001, "2": 2002, "3": 2003,
    "4": 2004, "5": 2005, "6": 2006, "7": 2007, "8": 2008, "9": 2009,
}

WMI_MAP = {
    "JN1": {"brand": "Nissan", "market": "Japan"},
    "JN6": {"brand": "Nissan", "market": "Japan"},
    "JTD": {"brand": "Toyota", "market": "Japan"},
    "JTE": {"brand": "Toyota", "market": "Japan"},
    "JZA": {"brand": "Toyota", "market": "Japan"},
    "VF3": {"brand": "Peugeot", "market": "Europe"},
    "WDB": {"brand": "Mercedes-Benz", "market": "Europe"},
    "WDC": {"brand": "Mercedes-Benz", "market": "Europe"},
}

ROOT_DIR = Path(__file__).resolve().parents[2]
JDM_CHASSIS_DATA_PATH = ROOT_DIR / "data" / "jdm_chassis_codes.json"
LOOKUP_NOTE_KEY = "_puls_vehicle_lookup"


class VehicleLookupResult(BaseModel):
    status: str = "not_found"
    confidence: float = 0.0
    source: str = ""
    brand: str | None = None
    model: str | None = None
    year: str | None = None
    year_range: str | None = None
    engine: str | None = None
    possible_models: list[str] = Field(default_factory=list)
    possible_engines: list[str] = Field(default_factory=list)
    chassis_code: str | None = None
    vin: str | None = None
    market: str | None = None
    needs_confirmation: bool = True
    raw_identifier: str = ""
    normalized_identifier: str = ""
    identifier_type: str = ""
    transmission: str | None = None
    drive: str | None = None
    fuel: str | None = None
    notes: str | None = None

    def to_vehicle_payload(self) -> dict[str, str]:
        return {
            "brand": self.brand or "",
            "model": self.model or "",
            "year": self.year or "",
            "engine": self.engine or "",
            "fuel": self.fuel or "",
            "fuel_type": self.fuel or "",
            "transmission": self.transmission or "",
            "drive": self.drive or "",
            "vin": self.raw_identifier or "",
            "market": self.market or "",
        }


class IdentifierContext(BaseModel):
    raw_identifier: str
    normalized_identifier: str
    compact_identifier: str
    identifier_type: str
    chassis_code: str


class VehicleLookupProvider(ABC):
    @abstractmethod
    async def lookup(self, identifier: str, context: IdentifierContext) -> VehicleLookupResult | None:
        raise NotImplementedError


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_year(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) < 4:
        return ""
    year = int(digits[:4])
    if year < 1981 or year > CURRENT_YEAR_MAX:
        return ""
    return str(year)


def _extract_json(text: str) -> dict[str, Any]:
    candidate = _clean_text(text)
    match = re.search(r"\{[\s\S]*\}", candidate)
    if match:
        candidate = match.group(0)
    data = json.loads(candidate)
    if not isinstance(data, dict):
        raise ValueError("Vehicle lookup response is not a JSON object.")
    return data


def _load_jdm_dictionary() -> dict[str, Any]:
    if not JDM_CHASSIS_DATA_PATH.exists():
        return {}
    try:
        return json.loads(JDM_CHASSIS_DATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def normalize_identifier(raw_identifier: str) -> IdentifierContext:
    raw = str(raw_identifier or "")
    trimmed = raw.strip().upper()
    compact_spaces = INNER_SPACES_PATTERN.sub("", trimmed)
    normalized = compact_spaces
    compact = compact_spaces.replace("-", "")

    if not FULL_VIN_PATTERN.fullmatch(compact_spaces):
        spaced_match = re.fullmatch(r"([A-Z0-9]{2,8})\s+(\d{4,8})", trimmed)
        if spaced_match:
            normalized = f"{spaced_match.group(1)}-{spaced_match.group(2)}"
            compact = f"{spaced_match.group(1)}{spaced_match.group(2)}"
        elif compact_spaces.count("-") == 0:
            compact_match = JDM_CHASSIS_COMPACT_PATTERN.fullmatch(compact_spaces)
            if compact_match:
                normalized = f"{compact_match.group(1)}-{compact_match.group(2)}"
                compact = f"{compact_match.group(1)}{compact_match.group(2)}"
        elif compact_spaces.count("-") == 1:
            hyphen_match = JDM_CHASSIS_WITH_HYPHEN_PATTERN.fullmatch(compact_spaces)
            if hyphen_match:
                normalized = f"{hyphen_match.group(1)}-{hyphen_match.group(2)}"
                compact = f"{hyphen_match.group(1)}{hyphen_match.group(2)}"

    identifier_type = detect_identifier_type(normalized)
    chassis_code = extract_jdm_chassis_code(normalized) if identifier_type == "jdm_chassis" else ""
    return IdentifierContext(
        raw_identifier=raw,
        normalized_identifier=normalized,
        compact_identifier=compact,
        identifier_type=identifier_type,
        chassis_code=chassis_code,
    )


def detect_identifier_type(identifier: str) -> str:
    normalized = _clean_text(identifier).upper()
    compact = normalized.replace("-", "")
    if FULL_VIN_PATTERN.fullmatch(compact):
        return "vin"
    if (
        normalized
        and len(compact) < 17
        and VALID_IDENTIFIER_CHARS_PATTERN.fullmatch(normalized)
        and (
            JDM_CHASSIS_WITH_HYPHEN_PATTERN.fullmatch(normalized)
            or JDM_CHASSIS_COMPACT_PATTERN.fullmatch(compact)
        )
    ):
        return "jdm_chassis"
    return "unknown"


def extract_jdm_chassis_code(identifier: str) -> str:
    normalized = _clean_text(identifier).upper()
    compact = normalized.replace("-", "")
    match = JDM_CHASSIS_WITH_HYPHEN_PATTERN.fullmatch(normalized)
    if match:
        return match.group(1)
    compact_match = JDM_CHASSIS_COMPACT_PATTERN.fullmatch(compact)
    if compact_match:
        return compact_match.group(1)
    return ""


def _safe_query(operation, default=None):
    if not is_supabase_configured():
        return default
    try:
        return operation()
    except (SupabaseUnavailableError, SupabaseOperationError):
        return default
    except Exception:
        return default


def _parse_lookup_meta_from_notes(notes: Any) -> dict[str, Any]:
    raw_notes = str(notes or "").strip()
    if not raw_notes:
        return {}
    try:
        parsed = json.loads(raw_notes)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    meta = parsed.get(LOOKUP_NOTE_KEY)
    return meta if isinstance(meta, dict) else {}


class NhtsaVinProvider(VehicleLookupProvider):
    def __init__(self, endpoint: str, source_name: str) -> None:
        self.endpoint = endpoint
        self.source_name = source_name

    async def lookup(self, identifier: str, context: IdentifierContext) -> VehicleLookupResult | None:
        if context.identifier_type != "vin":
            return None
        url = f"https://vpic.nhtsa.dot.gov/api/vehicles/{self.endpoint}/{context.compact_identifier}?format=json"
        async with httpx.AsyncClient(timeout=18) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
        results = payload.get("Results") or []
        if not isinstance(results, list) or not results:
            return None
        record = results[0] or {}
        brand = _clean_text(record.get("Make") or record.get("Manufacturer") or record.get("ManufacturerName"))
        model = _clean_text(record.get("Model") or record.get("BaseModelName") or record.get("ModelName") or record.get("Series") or record.get("Trim"))
        year = _normalize_year(record.get("ModelYear"))
        if not (brand or model or year):
            return None
        return VehicleLookupResult(
            status="confirmed" if brand and model else "probable",
            confidence=0.92 if brand and model and year else 0.72,
            source=self.source_name,
            brand=brand or None,
            model=model or None,
            year=year or None,
            vin=context.raw_identifier,
            raw_identifier=context.raw_identifier,
            normalized_identifier=context.normalized_identifier,
            identifier_type=context.identifier_type,
            needs_confirmation=True,
        )


class LocalVinDecoderProvider(VehicleLookupProvider):
    async def lookup(self, identifier: str, context: IdentifierContext) -> VehicleLookupResult | None:
        if context.identifier_type != "vin":
            return None
        wmi = context.compact_identifier[:3]
        wmi_data = WMI_MAP.get(wmi)
        year_code = context.compact_identifier[9] if len(context.compact_identifier) >= 10 else ""
        year = str(YEAR_CODE_MAP.get(year_code, "")) if year_code in YEAR_CODE_MAP else ""
        if not wmi_data and not year:
            return None
        return VehicleLookupResult(
            status="probable",
            confidence=0.45 if (wmi_data and year) else 0.3,
            source="local_wmi",
            brand=(wmi_data or {}).get("brand"),
            market=(wmi_data or {}).get("market"),
            year=year or None,
            vin=context.raw_identifier,
            raw_identifier=context.raw_identifier,
            normalized_identifier=context.normalized_identifier,
            identifier_type=context.identifier_type,
            needs_confirmation=True,
        )


class LocalJdmDictionaryProvider(VehicleLookupProvider):
    def __init__(self) -> None:
        self.dictionary = _load_jdm_dictionary()

    async def lookup(self, identifier: str, context: IdentifierContext) -> VehicleLookupResult | None:
        if context.identifier_type != "jdm_chassis" or not context.chassis_code:
            return None
        record = self.dictionary.get(context.chassis_code)
        if not isinstance(record, dict):
            return None
        models = [str(item).strip() for item in record.get("models") or [] if str(item).strip()]
        engines = [str(item).strip() for item in record.get("possible_engines") or [] if str(item).strip()]
        status = "ambiguous" if len(models) > 1 or len(engines) > 1 else "probable"
        return VehicleLookupResult(
            status=status,
            confidence=0.84 if status == "probable" else 0.6,
            source="local_dictionary",
            brand=_clean_text(record.get("brand")) or None,
            model=models[0] if len(models) == 1 else None,
            year_range=_clean_text(record.get("years")) or None,
            engine=engines[0] if len(engines) == 1 else None,
            possible_models=models,
            possible_engines=engines,
            chassis_code=context.chassis_code,
            vin=context.raw_identifier,
            market=_clean_text(record.get("market")) or None,
            raw_identifier=context.raw_identifier,
            normalized_identifier=context.normalized_identifier,
            identifier_type=context.identifier_type,
            needs_confirmation=True,
        )


class PulsDatabaseLookupProvider(VehicleLookupProvider):
    async def lookup(self, identifier: str, context: IdentifierContext) -> VehicleLookupResult | None:
        rows = _safe_query(lambda: self._fetch_candidate_rows(context), [])
        if not rows:
            return None

        brands = {row.get("brand") for row in rows if row.get("brand")}
        models = {row.get("model") for row in rows if row.get("model")}
        engines = {row.get("engine") for row in rows if row.get("engine")}
        years = {str(row.get("year")) for row in rows if row.get("year")}
        markets = {row.get("market") for row in rows if row.get("market")}
        confirmed_rows = [row for row in rows if row.get("user_confirmed")]

        status = "ambiguous"
        if len(models) <= 1 and len(engines) <= 1:
            status = "confirmed" if confirmed_rows else "probable"
        return VehicleLookupResult(
            status=status,
            confidence=0.97 if status == "confirmed" else 0.78 if status == "probable" else 0.5,
            source="puls_database",
            brand=next(iter(brands), None) if len(brands) == 1 else None,
            model=next(iter(models), None) if len(models) == 1 else None,
            year=next(iter(years), None) if len(years) == 1 else None,
            year_range=None,
            engine=next(iter(engines), None) if len(engines) == 1 else None,
            possible_models=sorted(models),
            possible_engines=sorted(engines),
            chassis_code=context.chassis_code or None,
            vin=context.raw_identifier,
            market=next(iter(markets), None) if len(markets) == 1 else None,
            raw_identifier=context.raw_identifier,
            normalized_identifier=context.normalized_identifier,
            identifier_type=context.identifier_type,
            needs_confirmation=status != "confirmed",
        )

    def _fetch_candidate_rows(self, context: IdentifierContext) -> list[dict[str, Any]]:
        client = get_supabase_client()
        vehicle_response = client.table("vehicles").select("*").order("updated_at", desc=True).limit(200).execute()
        vehicles = getattr(vehicle_response, "data", []) or []
        matches: list[dict[str, Any]] = []
        matched_vehicle_ids: set[int] = set()

        for row in vehicles:
            row_identifier = _clean_text(row.get("vin")).upper()
            lookup_meta = _parse_lookup_meta_from_notes(row.get("notes"))
            meta_normalized = _clean_text(lookup_meta.get("normalized_identifier")).upper()
            meta_type = _clean_text(lookup_meta.get("identifier_type"))
            meta_chassis = _clean_text(lookup_meta.get("chassis_code")).upper()
            if context.identifier_type == "vin" and row_identifier == context.compact_identifier:
                matches.append(
                    {
                        "brand": row.get("brand"),
                        "model": row.get("model"),
                        "year": row.get("year"),
                        "engine": row.get("engine"),
                        "market": lookup_meta.get("market"),
                        "user_confirmed": bool(lookup_meta.get("user_confirmed")),
                    }
                )
                if row.get("id"):
                    matched_vehicle_ids.add(int(row["id"]))
            elif (
                context.identifier_type == "jdm_chassis"
                and meta_type == "jdm_chassis"
                and (meta_normalized == context.normalized_identifier or meta_chassis == context.chassis_code)
            ):
                matches.append(
                    {
                        "brand": row.get("brand"),
                        "model": row.get("model"),
                        "year": row.get("year"),
                        "engine": row.get("engine"),
                        "market": lookup_meta.get("market"),
                        "user_confirmed": bool(lookup_meta.get("user_confirmed")),
                    }
                )
                if row.get("id"):
                    matched_vehicle_ids.add(int(row["id"]))

        if matched_vehicle_ids:
            solved_response = client.table("solved_cases").select("vehicle_id,brand,model,year,engine").in_("vehicle_id", list(matched_vehicle_ids)).limit(100).execute()
            for row in getattr(solved_response, "data", []) or []:
                matches.append(
                    {
                        "brand": row.get("brand"),
                        "model": row.get("model"),
                        "year": row.get("year"),
                        "engine": row.get("engine"),
                        "market": "",
                        "user_confirmed": True,
                    }
                )
        return matches


class OpenWebSearchProvider(VehicleLookupProvider):
    async def lookup(self, identifier: str, context: IdentifierContext) -> VehicleLookupResult | None:
        if not is_configured():
            return None

        queries = self._build_queries(context)
        if not queries:
            return None

        instructions = (
            "You are an automotive identification researcher. Use only open web search. "
            "For a VIN, identify brand/model/year only when supported by evidence. "
            "For a Japanese chassis code, determine brand, market, possible models, year range, and possible engines. "
            "Do not guess. If there are multiple models or engines, return all known options. "
            "Do not treat classifieds as the only source of truth. Prefer reference pages, forums discussing chassis codes, "
            "manufacturer pages, or widely known encyclopedic sources. "
            "Return only JSON."
        )
        payload = json.dumps({"queries": queries, "identifier": context.normalized_identifier}, ensure_ascii=False)
        try:
            response = get_openai_client().responses.create(
                model="gpt-4.1-mini",
                instructions=instructions,
                input=payload,
                tools=[{"type": "web_search_preview", "search_context_size": "medium"}],
                max_output_tokens=1200,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "vehicle_lookup_web",
                        "description": "Open web lookup result.",
                        "schema": VEHICLE_LOOKUP_SCHEMA,
                        "strict": True,
                    }
                },
            )
            data = _extract_json(getattr(response, "output_text", "") or "")
        except (OpenAIRouterUnavailableError, Exception):
            return None

        models = [str(item).strip() for item in data.get("possible_models") or [] if str(item).strip()]
        engines = [str(item).strip() for item in data.get("possible_engines") or [] if str(item).strip()]
        sources_confirmed = int(data.get("sources_confirmed") or 0)
        if not (_clean_text(data.get("brand")) or models):
            return None
        status = "probable"
        if len(models) > 1 or len(engines) > 1:
            status = "ambiguous"
        return VehicleLookupResult(
            status=status,
            confidence=0.7 if sources_confirmed >= 2 and status == "probable" else 0.52 if status == "probable" else 0.45,
            source="web_search",
            brand=_clean_text(data.get("brand")) or None,
            model=models[0] if len(models) == 1 else None,
            year_range=_clean_text(data.get("year_range")) or None,
            engine=engines[0] if len(engines) == 1 else None,
            possible_models=models,
            possible_engines=engines,
            chassis_code=context.chassis_code or None,
            vin=context.raw_identifier,
            market=_clean_text(data.get("market")) or None,
            raw_identifier=context.raw_identifier,
            normalized_identifier=context.normalized_identifier,
            identifier_type=context.identifier_type,
            needs_confirmation=True,
            notes=_clean_text(data.get("notes")) or None,
        )

    def _build_queries(self, context: IdentifierContext) -> list[str]:
        if context.identifier_type == "jdm_chassis" and context.chassis_code:
            return [
                f"{context.chassis_code} chassis code model engine",
                f"{context.chassis_code} model",
                f"{context.chassis_code} 車台型式",
            ]
        if context.identifier_type == "vin":
            return [
                f"{context.compact_identifier} VIN decoder",
                f"{context.compact_identifier} make model year",
            ]
        return []


class VehicleLookupService:
    def __init__(self) -> None:
        self.jdm_dictionary_provider = LocalJdmDictionaryProvider()
        self.puls_provider = PulsDatabaseLookupProvider()
        self.vin_providers: list[VehicleLookupProvider] = [
            NhtsaVinProvider("DecodeVinValuesExtended", "free_vin_api"),
            NhtsaVinProvider("DecodeVinValues", "free_vin_api_backup"),
            LocalVinDecoderProvider(),
        ]
        self.jdm_providers: list[VehicleLookupProvider] = [
            self.jdm_dictionary_provider,
            self.puls_provider,
            OpenWebSearchProvider(),
        ]

    def normalize_identifier(self, raw_identifier: str) -> IdentifierContext:
        return normalize_identifier(raw_identifier)

    def detect_identifier_type(self, identifier: str) -> str:
        return detect_identifier_type(identifier)

    def extract_jdm_chassis_code(self, identifier: str) -> str:
        return extract_jdm_chassis_code(identifier)

    async def lookup(self, raw_identifier: str) -> VehicleLookupResult:
        context = self.normalize_identifier(raw_identifier)
        if context.identifier_type == "vin":
            return await self.lookup_vin(context)
        if context.identifier_type == "jdm_chassis":
            return await self.lookup_jdm_chassis(context)
        return VehicleLookupResult(
            status="not_found",
            confidence=0.0,
            source="",
            raw_identifier=context.raw_identifier,
            normalized_identifier=context.normalized_identifier,
            identifier_type=context.identifier_type,
            needs_confirmation=True,
        )

    async def lookup_vin(self, context: IdentifierContext) -> VehicleLookupResult:
        db_result = await self.lookup_puls_database(context.raw_identifier)
        if db_result and db_result.status == "confirmed":
            return db_result

        collected: list[VehicleLookupResult] = [db_result] if db_result else []
        for provider in self.vin_providers:
            result = await provider.lookup(context.raw_identifier, context)
            if result:
                collected.append(result)
                if result.status == "confirmed":
                    return self.merge_results(collected, context)
        return self.merge_results(collected, context)

    async def lookup_jdm_chassis(self, context: IdentifierContext) -> VehicleLookupResult:
        dict_result = await self.jdm_dictionary_provider.lookup(context.raw_identifier, context)
        db_result = await self.lookup_puls_database(context.raw_identifier)
        if db_result and db_result.status == "confirmed":
            return db_result

        collected: list[VehicleLookupResult] = []
        if db_result:
            collected.append(db_result)
        if dict_result:
            collected.append(dict_result)

        if (db_result and db_result.status == "probable") or (dict_result and dict_result.status == "probable"):
            return self.merge_results(collected, context)

        web_result = await self.lookup_web(context.raw_identifier)
        if web_result:
            collected.append(web_result)
        return self.merge_results(collected, context)

    def lookup_local_dictionary(self, identifier: str) -> VehicleLookupResult | None:
        context = self.normalize_identifier(identifier)
        if context.identifier_type != "jdm_chassis":
            return None
        record = self.jdm_dictionary_provider.dictionary.get(context.chassis_code)
        if not isinstance(record, dict):
            return None
        models = [str(item).strip() for item in record.get("models") or [] if str(item).strip()]
        engines = [str(item).strip() for item in record.get("possible_engines") or [] if str(item).strip()]
        return VehicleLookupResult(
            status="ambiguous" if len(models) > 1 or len(engines) > 1 else "probable",
            confidence=0.84 if len(models) == 1 and len(engines) <= 1 else 0.6,
            source="local_dictionary",
            brand=_clean_text(record.get("brand")) or None,
            model=models[0] if len(models) == 1 else None,
            year_range=_clean_text(record.get("years")) or None,
            engine=engines[0] if len(engines) == 1 else None,
            possible_models=models,
            possible_engines=engines,
            chassis_code=context.chassis_code or None,
            vin=context.raw_identifier,
            market=_clean_text(record.get("market")) or None,
            raw_identifier=context.raw_identifier,
            normalized_identifier=context.normalized_identifier,
            identifier_type=context.identifier_type,
            needs_confirmation=True,
        )

    async def lookup_puls_database(self, identifier: str) -> VehicleLookupResult | None:
        context = self.normalize_identifier(identifier)
        return await self.puls_provider.lookup(identifier, context)

    async def lookup_web(self, identifier: str) -> VehicleLookupResult | None:
        context = self.normalize_identifier(identifier)
        return await OpenWebSearchProvider().lookup(identifier, context)

    def merge_results(self, results: list[VehicleLookupResult | None], context: IdentifierContext) -> VehicleLookupResult:
        filtered = [result for result in results if result]
        if not filtered:
            return VehicleLookupResult(
                status="not_found",
                confidence=0.0,
                source="",
                raw_identifier=context.raw_identifier,
                normalized_identifier=context.normalized_identifier,
                identifier_type=context.identifier_type,
                chassis_code=context.chassis_code or None,
                vin=context.raw_identifier,
                needs_confirmation=True,
            )

        confirmed = [result for result in filtered if result.status == "confirmed"]
        if confirmed:
            return confirmed[0]

        if context.identifier_type == "jdm_chassis":
            model_pool = sorted({item for result in filtered for item in ([result.model] if result.model else []) + result.possible_models if item})
            engine_pool = sorted({item for result in filtered for item in ([result.engine] if result.engine else []) + result.possible_engines if item})
            brand_pool = {result.brand for result in filtered if result.brand}
            market_pool = {result.market for result in filtered if result.market}
            year_ranges = [result.year_range for result in filtered if result.year_range]
            if len(model_pool) > 1 or len(engine_pool) > 1:
                return VehicleLookupResult(
                    status="ambiguous",
                    confidence=self.calculate_confidence(filtered),
                    source=filtered[0].source,
                    brand=next(iter(brand_pool), None) if len(brand_pool) == 1 else None,
                    possible_models=model_pool,
                    possible_engines=engine_pool,
                    year_range=year_ranges[0] if year_ranges else None,
                    chassis_code=context.chassis_code or None,
                    vin=context.raw_identifier,
                    market=next(iter(market_pool), None) if len(market_pool) == 1 else None,
                    raw_identifier=context.raw_identifier,
                    normalized_identifier=context.normalized_identifier,
                    identifier_type=context.identifier_type,
                    needs_confirmation=True,
                )
            best = max(filtered, key=lambda item: item.confidence)
            best.confidence = self.calculate_confidence(filtered)
            return best

        best = max(filtered, key=lambda item: item.confidence)
        best.confidence = self.calculate_confidence(filtered)
        return best

    def calculate_confidence(self, results: list[VehicleLookupResult]) -> float:
        if not results:
            return 0.0
        best = max(result.confidence for result in results)
        if len(results) == 1:
            return round(best, 2)
        unique_models = {result.model for result in results if result.model}
        if len(unique_models) > 1:
            return round(min(best, 0.55), 2)
        return round(min(best + 0.05, 0.99), 2)


vehicle_lookup_service = VehicleLookupService()
