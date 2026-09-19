import asyncio
import copy
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.main import app
from app.routers import admin
from app.services import knowledge_library_service as library


class _Response:
    def __init__(self, data):
        self.data = data


class _WriteQuery:
    def __init__(self, sink, payload):
        self.sink = sink
        self.payload = payload

    def eq(self, *_args):
        return self

    def execute(self):
        self.sink.append(copy.deepcopy(self.payload))
        return _Response([{"id": "saved", **self.payload}])


class _ReadQuery:
    def eq(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        return _Response([])


class _Table:
    def __init__(self, sink):
        self.sink = sink

    def update(self, payload):
        return _WriteQuery(self.sink, payload)

    def insert(self, payload):
        return _WriteQuery(self.sink, payload)

    def select(self, *_args, **_kwargs):
        return _ReadQuery()


class _Client:
    def __init__(self, sink):
        self.sink = sink

    def table(self, _name):
        return _Table(self.sink)


class KnowledgeLibraryTests(unittest.TestCase):
    def test_library_routes_are_admin_only_and_include_management_methods(self):
        routes = [route for route in app.routes if route.path.startswith("/admin/knowledge/library/")]
        methods = {(route.path, method) for route in routes for method in route.methods}
        self.assertIn(("/admin/knowledge/library/items", "GET"), methods)
        self.assertIn(("/admin/knowledge/library/items", "POST"), methods)
        self.assertIn(("/admin/knowledge/library/items/{item_id}", "PATCH"), methods)
        self.assertIn(("/admin/knowledge/library/items/{item_id}", "DELETE"), methods)
        self.assertIn(("/admin/knowledge/library/vehicles/{vehicle_id}", "DELETE"), methods)
        self.assertIn(("/admin/knowledge/library/successful-cases/{case_id}", "DELETE"), methods)
        with patch.object(admin, "require_admin", side_effect=HTTPException(status_code=403)) as require, patch.object(
            admin, "knowledge_catalog"
        ) as catalog:
            with self.assertRaises(HTTPException):
                asyncio.run(admin.admin_knowledge_catalog(object()))
        require.assert_called_once()
        catalog.assert_not_called()
        with patch.object(admin, "require_admin", side_effect=HTTPException(status_code=403)) as require_delete, patch.object(
            admin, "hard_delete_vehicle"
        ) as delete_vehicle:
            with self.assertRaises(HTTPException):
                asyncio.run(admin.admin_delete_vehicle("vehicle-1", object()))
        require_delete.assert_called_once()
        delete_vehicle.assert_not_called()

    def test_manual_payload_uses_normalized_applicability_and_pending_review(self):
        with patch.object(library, "find_or_create_configuration", return_value={"id": "cfg-307"}):
            payload, source = library.build_material_payload({
                "title": "Peugeot 307 workshop manual",
                "knowledge_type": "MANUAL",
                "description": "Workshop procedures",
                "url": "https://manual.example.test/307",
                "source_type": "MANUAL",
                "applicability": {"make": "Peugeot", "model": "307"},
            })
        self.assertEqual(payload["vehicle_configuration_id"], "cfg-307")
        self.assertEqual(payload["knowledge_type"], "MANUAL")
        self.assertEqual(payload["validation_status"], "UNVERIFIED")
        self.assertEqual(payload["metadata"]["review_status"], "PENDING_REVIEW")
        self.assertEqual(payload["metadata"]["provenance_type"], "MANUAL")
        self.assertNotIn("provenance_type", payload)
        self.assertEqual(source["url"], "https://manual.example.test/307")

    def test_specific_and_general_knowledge_remain_distinct(self):
        with patch.object(library, "find_or_create_configuration", return_value={"id": "cfg-specific"}) as resolve:
            specific, _ = library.build_material_payload({
                "title": "AL4 pressure check", "knowledge_type": "PROCEDURE",
                "applicability": {"make": "Peugeot", "model": "307", "year_from": 2004, "year_to": 2004, "engine": "TU5JP4"},
            })
        general, _ = library.build_material_payload({"title": "Voltage drop basics", "knowledge_type": "GENERAL"})
        self.assertEqual(specific["vehicle_configuration_id"], "cfg-specific")
        self.assertEqual(specific["knowledge_type"], "TECHNICAL_REFERENCE")
        self.assertEqual(specific["metadata"]["material_type"], "PROCEDURE")
        self.assertIsNone(general["vehicle_configuration_id"])
        self.assertEqual(resolve.call_args.args[0]["year_from"], 2004)

    def test_mechanic_review_preserves_original_case(self):
        original_case = {"symptoms": ["slips hot"], "result": "repair confirmed"}
        existing = {"id": "knowledge-1", "metadata": {"original_case": copy.deepcopy(original_case)}, "symptoms": ["raw symptom"]}
        writes = []
        with patch.object(library, "_get_row", return_value=existing), patch.object(
            library, "get_supabase_client", return_value=_Client(writes)
        ), patch.object(library, "get_material", return_value={"id": "knowledge-1"}):
            library.review_candidate("KNOWLEDGE", "knowledge-1", {
                "decision": "VERIFIED", "technical_comment": "Confirmed by mechanic",
                "normalized_symptoms": ["automatic transmission slips after warm-up"],
            })
        self.assertEqual(existing["metadata"]["original_case"], original_case)
        self.assertEqual(writes[0]["metadata"]["original_case"], original_case)
        self.assertEqual(writes[0]["metadata"]["mechanic_review"]["decision"], "VERIFIED")
        self.assertEqual(writes[0]["symptoms"], ["automatic transmission slips after warm-up"])

    def test_successful_case_review_creates_candidate_without_mutating_origin(self):
        original = {
            "id": "fleet-1", "vehicle_configuration_id": "cfg-1",
            "symptoms": ["No hot drive"], "conditions": {"temperature": "hot"},
            "cause": "pressure loss", "action": "valve body repair", "result": "HELPED",
            "confirmation_status": "CONFIRMED", "confidence": 0.9,
        }
        frozen = copy.deepcopy(original)
        writes = []
        with patch.object(library, "_get_row", return_value=original), patch.object(
            library, "get_supabase_client", return_value=_Client(writes)
        ), patch.object(library, "get_material", return_value={"id": "saved"}):
            library.review_candidate("SUCCESSFUL_CASE", "fleet-1", {"decision": "VERIFIED", "verification_note": "Result confirmed"})
        self.assertEqual(original, frozen)
        self.assertEqual(writes[0]["knowledge_type"], "PULS_CASE")
        self.assertEqual(writes[0]["metadata"]["material_type"], "SUCCESSFUL_CASE")
        self.assertEqual(writes[0]["solutions"], ["valve body repair"])
        self.assertEqual(writes[0]["metadata"]["original_case"], frozen)
        self.assertEqual(writes[0]["metadata"]["mechanic_review"]["decision"], "VERIFIED")

    def test_unsupported_material_type_fails_closed(self):
        with self.assertRaises(HTTPException):
            library.build_material_payload({"title": "Bad", "knowledge_type": "INVENTED_TYPE"})


if __name__ == "__main__":
    unittest.main()
