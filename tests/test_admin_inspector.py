import asyncio
import unittest
from unittest.mock import patch

from app.main import app
from app.routers import admin
from app.services import admin_inspector_service


class AdminInspectorTests(unittest.TestCase):
    def test_inspector_routes_are_read_only(self):
        routes = [
            route
            for route in app.routes
            if route.path.startswith("/admin/knowledge")
        ]

        self.assertGreaterEqual(len(routes), 10)
        for route in routes:
            self.assertEqual(set(route.methods), {"GET"})

    def test_overview_requires_admin_before_reading_data(self):
        with patch.object(admin, "require_admin", return_value="admin-id") as require, patch.object(
            admin, "get_overview", return_value={"counts": {}, "recent_conversations": []}
        ) as overview:
            result = asyncio.run(admin.admin_knowledge_overview(object()))

        require.assert_called_once()
        overview.assert_called_once_with()
        self.assertEqual(result["counts"], {})

    def test_child_rows_are_exposed_through_scoped_endpoints(self):
        with patch.object(admin, "require_admin", return_value="admin-id"), patch.object(
            admin,
            "list_conversation_messages",
            return_value={"items": [], "total": 0, "limit": 100, "offset": 0},
        ) as messages:
            asyncio.run(
                admin.admin_knowledge_conversation_messages(
                    "00000000-0000-4000-8000-000000000042", object(), limit=100, offset=0
                )
            )

        messages.assert_called_once_with(
            "00000000-0000-4000-8000-000000000042", limit=100, offset=0
        )

    def test_pagination_is_bounded(self):
        self.assertEqual(admin_inspector_service._safe_page(0, -5), (1, 0))
        self.assertEqual(admin_inspector_service._safe_page(1000, 12), (100, 12))

    def test_auxiliary_relation_failure_keeps_primary_rows(self):
        primary = [{"id": "conversation-1", "user_id": "user-1"}]
        with patch.object(
            admin_inspector_service,
            "_lookup_optional",
            side_effect=[
                ({}, "Related user metadata is unavailable; primary rows are still shown."),
                ({}, None),
                ({}, None),
            ],
        ):
            items, warnings = admin_inspector_service._enrich(primary)

        self.assertEqual(items[0]["id"], "conversation-1")
        self.assertIsNone(items[0]["user"])
        self.assertEqual(len(warnings), 1)

    def test_overview_reports_unavailable_values_instead_of_fake_zeroes(self):
        def count_table(table):
            if table == "knowledge_items":
                raise RuntimeError("unavailable")
            return 3

        with patch.object(admin_inspector_service, "_count_table", side_effect=count_table), patch.object(
            admin_inspector_service, "_count_filtered", return_value=1
        ), patch.object(
            admin_inspector_service, "_value_distribution", return_value={"FORUM": 2}
        ), patch.object(
            admin_inspector_service, "_recent_rows", return_value=[]
        ):
            result = admin_inspector_service.get_overview()

        self.assertIsNone(result["counts"]["knowledge_items"])
        self.assertIn("count.knowledge_items", result["errors"])
        self.assertEqual(result["counts"]["messages"], 3)
        self.assertEqual(result["distributions"]["source_type"], {"FORUM": 2})

    def test_vehicle_events_use_production_event_date_contract(self):
        page = {"items": [], "total": 0, "limit": 25, "offset": 0, "warnings": []}
        with patch.object(
            admin_inspector_service, "_list_rows", return_value=page
        ) as listing, patch.object(
            admin_inspector_service, "_attach_enrichment", side_effect=lambda value: value
        ):
            admin_inspector_service.list_vehicle_events(
                limit=25, offset=0, event_type=None, search=None
            )

        self.assertEqual(listing.call_args.kwargs["order_by"], "event_date")

    def test_source_relation_failure_does_not_hide_source_rows(self):
        page = {
            "items": [{"id": "source-1", "url": "https://example.test"}],
            "total": 1,
            "limit": 25,
            "offset": 0,
            "warnings": [],
        }
        with patch.object(
            admin_inspector_service, "_list_rows", return_value=page
        ), patch.object(
            admin_inspector_service, "get_supabase_client", side_effect=RuntimeError("relation unavailable")
        ):
            result = admin_inspector_service.list_sources(
                limit=25, offset=0, source_type=None, search=None
            )

        self.assertEqual(result["items"][0]["id"], "source-1")
        self.assertEqual(result["items"][0]["problem_sources"], [])
        self.assertTrue(result["warnings"])


if __name__ == "__main__":
    unittest.main()
