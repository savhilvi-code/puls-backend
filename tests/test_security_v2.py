import unittest
import asyncio
from unittest.mock import patch

from app.database import supabase
from app.main import app
from app.services import auth_service

USER_ID = "11111111-1111-4111-8111-111111111111"


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

    def test_verified_jwt_user_id_maps_to_public_user_id(self):
        existing = auth_service.UserRecord(id=USER_ID, email="a@example.com")
        with patch.object(auth_service, "_bearer_token", return_value="jwt"), \
            patch.object(auth_service, "get_auth_user_from_bearer", return_value={"id": USER_ID, "email": "a@example.com"}), \
            patch.object(auth_service, "find_user_by_id", return_value=existing) as find_user, \
            patch.object(auth_service, "ensure_user_subscription"):
            user = asyncio.run(auth_service.get_or_create_profile(request=object(), payload={"user_id": "attacker"}, require_auth=True))

        self.assertEqual(user.id, USER_ID)
        find_user.assert_called_once_with(USER_ID)

    def test_authenticated_profile_failure_does_not_become_transient(self):
        with patch.object(auth_service, "_bearer_token", return_value="jwt"), \
            patch.object(auth_service, "get_auth_user_from_bearer", return_value={"id": USER_ID, "email": "a@example.com"}), \
            patch.object(auth_service, "find_user_by_id", side_effect=supabase.SupabaseOperationError("profile failed")):
            with self.assertRaises(Exception) as raised:
                asyncio.run(auth_service.get_or_create_profile(request=object(), payload={}, require_auth=True))

        self.assertEqual(getattr(raised.exception, "status_code", None), 503)


if __name__ == "__main__":
    unittest.main()
