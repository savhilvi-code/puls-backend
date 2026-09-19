import unittest
from unittest.mock import call, patch

from app.services import admin_delete_service as delete_service


class AdminDeleteServiceTests(unittest.TestCase):
    def test_vehicle_preview_reports_cascade_detach_and_preserved_shared_layers(self):
        vehicle = {"id": "vehicle-1", "make": "Peugeot", "model": "307", "year": 2004, "photo_url": "https://storage/vehicle.jpg"}
        eq_values = {
            ("vehicle_specs", "vehicle_id"): ["spec-1"],
            ("problems", "vehicle_id"): ["problem-1"],
            ("vehicle_events", "vehicle_id"): ["event-1"],
            ("conversations", "vehicle_id"): ["conversation-1"],
        }
        in_values = {
            ("problem_sources", "problem_id"): ["problem-source-1"],
            ("search_episodes", "problem_id"): ["episode-1"],
            ("search_runs", "search_episode_id"): ["run-1"],
            ("messages", "conversation_id"): ["message-1", "message-2"],
            ("fleet_events", "origin_event_id"): ["case-1"],
            ("knowledge_items", "vehicle_configuration_id"): ["knowledge-config-1"],
            ("fleet_events", "vehicle_configuration_id"): ["fleet-config-1"],
        }
        with patch.object(delete_service, "_one", return_value=vehicle), patch.object(
            delete_service, "_ids_eq", side_effect=lambda table, column, _value: eq_values.get((table, column), [])
        ), patch.object(
            delete_service, "_ids_in", side_effect=lambda table, column, _values: in_values.get((table, column), [])
        ), patch.object(
            delete_service, "_ids_metadata_eq", return_value=["case-knowledge-1"]
        ), patch.object(
            delete_service, "_matching_configurations", return_value=[{"id": "config-1"}]
        ):
            preview = delete_service.preview_vehicle_delete("vehicle-1")

        self.assertEqual(preview["counts"]["search_runs"], 1)
        self.assertEqual(preview["counts"]["messages"], 2)
        self.assertEqual(preview["counts"]["matching_shared_vehicle_configurations"], 1)
        self.assertIn("vehicle_configurations", preview["effects"]["preserve"])
        self.assertEqual(preview["fk_basis"]["conversations"], "SET NULL")
        self.assertEqual(preview["storage"]["action"], "PRESERVE")

    def test_vehicle_delete_uses_single_root_delete_then_verifies_fk_cleanup(self):
        with patch.object(delete_service, "preview_vehicle_delete", return_value={"counts": {}}), patch.object(
            delete_service, "_delete_id"
        ) as remove, patch.object(delete_service, "_one", return_value=None), patch.object(
            delete_service, "_ids_eq", return_value=[]
        ):
            result = delete_service.delete_vehicle("vehicle-1")
        remove.assert_called_once_with("vehicles", "vehicle-1")
        self.assertTrue(all(result["verification"].values()))

    def test_material_delete_removes_relations_but_preserves_all_sources(self):
        preview = {"source_ids": ["source-1", "source-2"]}
        with patch.object(delete_service, "preview_knowledge_delete", return_value=preview), patch.object(
            delete_service, "_delete_id"
        ) as remove, patch.object(delete_service, "_one", return_value=None), patch.object(
            delete_service, "_ids_eq", return_value=[]
        ), patch.object(
            delete_service, "_rows_in", return_value=[{"id": "source-1"}, {"id": "source-2"}]
        ):
            result = delete_service.delete_knowledge_material("knowledge-1")
        remove.assert_called_once_with("knowledge_items", "knowledge-1")
        self.assertTrue(result["verification"]["sources_preserved"])

    def test_successful_case_delete_removes_promoted_items_before_case_and_keeps_sources(self):
        preview = {"knowledge_item_ids": ["knowledge-1"], "source_ids": ["source-1"]}
        with patch.object(delete_service, "preview_successful_case_delete", return_value=preview), patch.object(
            delete_service, "_delete_ids"
        ) as remove_many, patch.object(delete_service, "_delete_id") as remove_one, patch.object(
            delete_service, "_one", return_value=None
        ), patch.object(delete_service, "_ids_metadata_eq", return_value=[]), patch.object(
            delete_service, "_ids_in", return_value=[]
        ), patch.object(delete_service, "_rows_in", return_value=[{"id": "source-1"}]):
            result = delete_service.delete_successful_case("case-1")
        remove_many.assert_has_calls([call("knowledge_items", ["knowledge-1"])])
        remove_one.assert_called_once_with("fleet_events", "case-1")
        self.assertTrue(result["verification"]["sources_preserved"])


if __name__ == "__main__":
    unittest.main()
