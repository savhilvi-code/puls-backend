import unittest
from unittest.mock import patch

from app.services import subscription_service as subscriptions


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, rows=None):
        self.rows = rows if rows is not None else []
        self.calls = []

    def select(self, *args, **kwargs):
        self.calls.append(("select", args, kwargs))
        return self

    def insert(self, payload):
        self.calls.append(("insert", payload))
        self.rows = [{**payload, "id": 1}]
        return self

    def update(self, payload):
        self.calls.append(("update", payload))
        self.rows = [{**self.rows[0], **payload}] if self.rows else [payload]
        return self

    def eq(self, column, value):
        self.calls.append(("eq", column, value))
        return self

    def in_(self, column, value):
        self.calls.append(("in", column, value))
        return self

    def order(self, *args, **kwargs):
        self.calls.append(("order", args, kwargs))
        return self

    def limit(self, value):
        self.calls.append(("limit", value))
        return self

    def execute(self):
        return FakeResponse(self.rows)


class FakeClient:
    def __init__(self, rows):
        self.query = FakeQuery(rows)

    def table(self, name):
        self.table_name = name
        return self.query


class SubscriptionV2Tests(unittest.TestCase):
    def test_quota_payload_uses_quota_columns(self):
        payload = subscriptions.quota_payload({"plan": "free", "quota_limit": 10, "quota_used": 4})

        self.assertEqual(payload, {"remaining": 6, "used": 4, "limit": 10, "plan_type": "free", "unlimited": False})

    def test_legacy_request_columns_are_not_quota_source_of_truth(self):
        payload = subscriptions.quota_payload({"plan": "free", "requests_limit": 99, "requests_used": 98})

        self.assertEqual(payload, {"remaining": 5, "used": 0, "limit": 5, "plan_type": "free", "unlimited": False})

    def test_existing_custom_quota_is_not_silently_rewritten(self):
        client = FakeClient([{"id": 1, "user_id": 7, "plan": "free", "status": "active", "quota_limit": 3, "quota_used": 1}])
        with patch.object(subscriptions, "get_supabase_client", return_value=client):
            existing = subscriptions.ensure_user_subscription(user_id=7)
        self.assertEqual(existing["quota_limit"], 3)
        self.assertFalse(any(call[0] in {"insert", "update"} for call in client.query.calls))

    def test_consuming_research_credit_never_exceeds_limit(self):
        client = FakeClient([{"id": 1, "user_id": 7, "plan": "free", "status": "active", "quota_limit": 10, "quota_used": 10}])

        with patch.object(subscriptions, "get_supabase_client", return_value=client):
            updated = subscriptions.consume_research_credit(user_id=7)

        self.assertEqual(updated["quota_used"], 10)
        self.assertIn(("eq", "id", 1), client.query.calls)
        self.assertIn(("eq", "user_id", 7), client.query.calls)

    def test_new_subscription_uses_quota_columns(self):
        client = FakeClient([])

        with patch.object(subscriptions, "get_supabase_client", return_value=client):
            created = subscriptions.ensure_user_subscription(user_id=7)

        insert_call = next(call for call in client.query.calls if call[0] == "insert")
        self.assertEqual(insert_call[1]["quota_limit"], subscriptions.FREE_LIMIT)
        self.assertEqual(insert_call[1]["quota_used"], 0)
        self.assertEqual(created["remaining"], subscriptions.FREE_LIMIT)


if __name__ == "__main__":
    unittest.main()
