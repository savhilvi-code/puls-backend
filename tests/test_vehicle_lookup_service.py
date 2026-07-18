import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.routers import vehicles as vehicles_router
from app.services.vehicle_lookup_service import VehicleLookupResult, VehicleLookupService, detect_identifier_type, extract_jdm_chassis_code, normalize_identifier


class VehicleLookupNormalizationTests(unittest.TestCase):
    def test_normalize_full_vin_lowercase(self):
        context = normalize_identifier("jn1tbnt30u0001234")
        self.assertEqual(context.normalized_identifier, "JN1TBNT30U0001234")
        self.assertEqual(context.identifier_type, "vin")

    def test_normalize_jdm_with_space(self):
        context = normalize_identifier("JZX100 1234567")
        self.assertEqual(context.normalized_identifier, "JZX100-1234567")
        self.assertEqual(context.identifier_type, "jdm_chassis")
        self.assertEqual(context.chassis_code, "JZX100")

    def test_normalize_jdm_with_dash(self):
        context = normalize_identifier("jzx100-1234567")
        self.assertEqual(context.normalized_identifier, "JZX100-1234567")
        self.assertEqual(context.identifier_type, "jdm_chassis")

    def test_detect_unknown_identifier(self):
        self.assertEqual(detect_identifier_type("??"), "unknown")
        self.assertEqual(detect_identifier_type(""), "unknown")

    def test_extract_jdm_chassis_code(self):
        self.assertEqual(extract_jdm_chassis_code("PNT30-012345"), "PNT30")
        self.assertEqual(extract_jdm_chassis_code("GRS1800012345"), "GRS180")
        self.assertEqual(extract_jdm_chassis_code("E11321342"), "E11")
        self.assertEqual(extract_jdm_chassis_code("NZE1243008110"), "NZE124")
        self.assertEqual(extract_jdm_chassis_code("GS131087322"), "GS131")

    def test_normalize_lowercase_jdm_with_spaces(self):
        context = normalize_identifier("  pnt30 012345  ")
        self.assertEqual(context.normalized_identifier, "PNT30-012345")
        self.assertEqual(context.identifier_type, "jdm_chassis")
        self.assertEqual(context.chassis_code, "PNT30")


class VehicleLookupServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_vin_does_not_go_through_jdm_branch(self):
        service = VehicleLookupService()
        service.lookup_vin = AsyncMock(
            return_value=VehicleLookupResult(
                status="probable",
                confidence=0.8,
                source="free_vin_api",
                brand="Nissan",
                raw_identifier="JN1TBNT30U0001234",
                normalized_identifier="JN1TBNT30U0001234",
                identifier_type="vin",
            )
        )
        service.lookup_jdm_chassis = AsyncMock(return_value=None)

        await service.lookup("JN1TBNT30U0001234")

        service.lookup_vin.assert_awaited_once()
        service.lookup_jdm_chassis.assert_not_called()

    async def test_jdm_identifier_does_not_go_through_vin_branch(self):
        service = VehicleLookupService()
        service.lookup_vin = AsyncMock(return_value=None)
        service.lookup_jdm_chassis = AsyncMock(
            return_value=VehicleLookupResult(
                status="probable",
                confidence=0.8,
                source="local_dictionary",
                brand="Toyota",
                raw_identifier="JZX100-1234567",
                normalized_identifier="JZX100-1234567",
                identifier_type="jdm_chassis",
                chassis_code="JZX100",
            )
        )

        await service.lookup("JZX100-1234567")

        service.lookup_jdm_chassis.assert_awaited_once()
        service.lookup_vin.assert_not_called()

    async def test_full_vin_does_not_use_open_web_search_provider(self):
        service = VehicleLookupService()
        for provider in service.vin_providers:
            provider.lookup = AsyncMock(return_value=None)
        with patch("app.services.vehicle_lookup_service.OpenWebSearchProvider.lookup", new=AsyncMock(return_value=VehicleLookupResult(status="probable", confidence=0.4, source="web_search")) ) as web_lookup:
            result = await service.lookup("JN1TBNT30U0001234")
        web_lookup.assert_not_awaited()
        self.assertEqual(result.status, "not_found")

    def test_local_dictionary_returns_ambiguous_for_jzx100(self):
        service = VehicleLookupService()
        result = service.lookup_local_dictionary("JZX100-1234567")
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "ambiguous")
        self.assertIn("Chaser", result.possible_models)
        self.assertIn("Mark II", result.possible_models)

    def test_local_dictionary_returns_probable_for_pnt30(self):
        service = VehicleLookupService()
        result = service.lookup_local_dictionary("PNT30-012345")
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "probable")
        self.assertEqual(result.brand, "Nissan")
        self.assertEqual(result.model, "X-Trail")
        self.assertEqual(result.engine, "SR20VET")

    def test_local_dictionary_returns_probable_for_grs180(self):
        service = VehicleLookupService()
        result = service.lookup_local_dictionary("GRS180-0012345")
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "probable")
        self.assertEqual(result.brand, "Toyota")
        self.assertEqual(result.model, "Crown")

    def test_real_case_e11_returns_ambiguous_note(self):
        service = VehicleLookupService()
        result = service.lookup_local_dictionary("E11321342")
        self.assertIsNotNone(result)
        self.assertEqual(result.brand, "Nissan")
        self.assertEqual(result.model, "Note")
        self.assertEqual(result.status, "ambiguous")
        self.assertIn("HR15DE", result.possible_engines)

    def test_real_case_nze124_returns_probable_corolla(self):
        service = VehicleLookupService()
        result = service.lookup_local_dictionary("NZE1243008110")
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "probable")
        self.assertEqual(result.brand, "Toyota")
        self.assertEqual(result.model, "Corolla")
        self.assertEqual(result.engine, "1NZ-FE")

    def test_real_case_gs131_returns_probable_crown(self):
        service = VehicleLookupService()
        result = service.lookup_local_dictionary("GS131087322")
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "probable")
        self.assertEqual(result.brand, "Toyota")
        self.assertEqual(result.model, "Crown")
        self.assertEqual(result.engine, "1G")

    async def test_unknown_jdm_code_returns_not_found_without_web_or_db(self):
        service = VehicleLookupService()
        with patch.object(service, "lookup_puls_database", new=AsyncMock(return_value=None)), patch.object(service, "lookup_web", new=AsyncMock(return_value=None)):
            result = await service.lookup("ABC123-000999")
        self.assertEqual(result.status, "not_found")


class VehicleLookupMetadataTests(unittest.TestCase):
    def test_confirmed_lookup_metadata_is_packed_into_notes(self):
        payload = vehicles_router.VehiclePayload(
            vin="JZX100-1234567",
            brand="Toyota",
            model="Chaser",
            raw_identifier="JZX100 1234567",
            normalized_identifier="JZX100-1234567",
            identifier_type="jdm_chassis",
            chassis_code="JZX100",
            market="JDM",
            lookup_status="ambiguous",
            lookup_source="local_dictionary",
            lookup_confidence=0.6,
            year_range="1996-2001",
            user_confirmed=True,
        )
        packed = vehicles_router._pack_vehicle_notes(raw_notes="", payload=payload)
        spec_meta, lookup_meta, manual_note = vehicles_router._extract_vehicle_meta(packed)
        self.assertEqual(spec_meta, {})
        self.assertEqual(manual_note, "")
        self.assertEqual(lookup_meta["normalized_identifier"], "JZX100-1234567")
        self.assertTrue(lookup_meta["user_confirmed"])

    def test_lookup_result_draft_is_not_marked_confirmed_automatically(self):
        result = VehicleLookupResult(
            status="ambiguous",
            confidence=0.6,
            source="local_dictionary",
            brand="Toyota",
            raw_identifier="JZX100-1234567",
            normalized_identifier="JZX100-1234567",
            identifier_type="jdm_chassis",
            chassis_code="JZX100",
        )
        draft = vehicles_router._lookup_result_to_draft(result)
        self.assertFalse(draft["user_confirmed"])
        self.assertEqual(draft["lookup_status"], "ambiguous")


class VehicleLookupRouteTests(unittest.TestCase):
    def test_lookup_route_returns_result_envelope(self):
        fake_result = VehicleLookupResult(
            status="probable",
            confidence=0.84,
            source="local_dictionary",
            brand="Nissan",
            model="X-Trail",
            engine="SR20VET",
            year_range="2000-2007",
            chassis_code="PNT30",
            market="JDM",
            vin="PNT30-012345",
            raw_identifier="PNT30-012345",
            normalized_identifier="PNT30-012345",
            identifier_type="jdm_chassis",
            needs_confirmation=True,
        )
        with patch("app.routers.vehicles.vehicle_lookup_service.lookup", new=AsyncMock(return_value=fake_result)):
            client = TestClient(app)
            response = client.post("/api/vehicles/lookup", json={"vin": "PNT30-012345"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["result"]["status"], "probable")
        self.assertEqual(payload["result"]["brand"], "Nissan")
        self.assertEqual(payload["vehicle"]["model"], "X-Trail")


if __name__ == "__main__":
    unittest.main()
