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
                    42, object(), limit=100, offset=0
                )
            )

        messages.assert_called_once_with(42, limit=100, offset=0)

    def test_pagination_is_bounded(self):
        self.assertEqual(admin_inspector_service._safe_page(0, -5), (1, 0))
        self.assertEqual(admin_inspector_service._safe_page(1000, 12), (100, 12))


if __name__ == "__main__":
    unittest.main()
