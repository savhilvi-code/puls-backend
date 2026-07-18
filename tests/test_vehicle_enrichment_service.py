import unittest

from app.services.vehicle_enrichment_service import _extract_jdm_chassis_parts, _lookup_local_jdm_chassis, enrich_vehicle_profile


class VehicleEnrichmentJdmTests(unittest.TestCase):
    def test_extract_compact_e11_parts(self):
        code, serial = _extract_jdm_chassis_parts("E11321342")
        self.assertEqual(code, "E11")
        self.assertEqual(serial, "321342")

    def test_local_jdm_provider_returns_pnt30(self):
        result = _lookup_local_jdm_chassis("PNT30003457")
        self.assertEqual(result["brand"], "Nissan")
        self.assertEqual(result["model"], "X-Trail")
        self.assertEqual(result["engine"], "SR20VET")

    def test_local_jdm_provider_returns_e11(self):
        result = _lookup_local_jdm_chassis("E11321342")
        self.assertEqual(result["brand"], "Nissan")
        self.assertEqual(result["model"], "Note")
        self.assertEqual(result["year"], "2008")

    def test_local_jdm_provider_returns_nze124(self):
        result = _lookup_local_jdm_chassis("NZE1243008110")
        self.assertEqual(result["brand"], "Toyota")
        self.assertEqual(result["model"], "Corolla")
        self.assertEqual(result["engine"], "1NZ-FE")

    def test_enrich_vehicle_profile_prefers_local_jdm_provider(self):
        result = enrich_vehicle_profile({"vin": "GS131087322"})
        self.assertEqual(result["brand"], "Toyota")
        self.assertEqual(result["model"], "Crown")
        self.assertEqual(result["engine"], "1G")


if __name__ == "__main__":
    unittest.main()
