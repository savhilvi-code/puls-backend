import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.history import router as history_router


class QuotaRouteTests(unittest.TestCase):
    def test_quota_route_returns_backend_subscription_state(self):
        user = SimpleNamespace(id=7)
        subscription = {"requests_limit": 10, "requests_used": 4, "plan": "free"}

        test_app = FastAPI()
        test_app.include_router(history_router)

        with (
            patch("app.routers.history.get_user_by_id", return_value=user),
            patch("app.routers.history.find_user_by_fields") as find_user,
            patch("app.routers.history.ensure_user_subscription", return_value=subscription),
        ):
            response = TestClient(test_app).get("/api/quota?user_id=7")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["quota"], {"remaining": 6, "used": 4, "limit": 10, "plan_type": "free", "unlimited": False})
        find_user.assert_not_called()


if __name__ == "__main__":
    unittest.main()
