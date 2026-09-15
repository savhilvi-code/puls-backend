import unittest
from unittest.mock import patch

from app.database import supabase
from app.main import app


class SecurityV2Tests(unittest.TestCase):
    def test_publishable_supabase_key_is_not_server_write_configuration(self):
        with patch.dict(
            "os.environ",
            {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_KEY": "sb_publishable_test"},
            clear=True,
        ):
            self.assertFalse(supabase.is_supabase_configured())
            self.assertEqual(supabase.supabase_key_source(), "publishable_key_ignored_for_server_writes")

    def test_service_role_key_is_server_configuration(self):
        with patch.dict(
            "os.environ",
            {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_test"},
            clear=True,
        ):
            self.assertTrue(supabase.is_supabase_configured())
            self.assertTrue(supabase.is_supabase_service_key_configured())
            self.assertEqual(supabase.supabase_key_source(), "SUPABASE_SERVICE_ROLE_KEY")

    def test_no_payment_mutation_route_is_exposed_to_normal_clients(self):
        mutable_payment_routes = [
            route.path
            for route in app.routes
            if "payment" in route.path.lower() and bool({"POST", "PUT", "PATCH", "DELETE"} & set(getattr(route, "methods", set())))
        ]
        self.assertEqual(mutable_payment_routes, [])

    def test_admin_operations_are_not_exposed_as_routes(self):
        forbidden = {"admin_set_user_limit", "admin_purge_user", "admin_users"}
        exposed = [route.path for route in app.routes if any(term in route.path for term in forbidden)]
        self.assertEqual(exposed, [])


if __name__ == "__main__":
    unittest.main()
