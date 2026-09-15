import unittest
from unittest.mock import patch

from app.services import v2_repository as repo

USER_ID = "11111111-1111-4111-8111-111111111111"
VEHICLE_ID = "22222222-2222-4222-8222-222222222222"
PROBLEM_ID = "33333333-3333-4333-8333-333333333333"


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, table_name, data=None):
        self.table_name = table_name
        self.calls = []
        self.data = data if data is not None else [{"id": VEHICLE_ID, "user_id": USER_ID}]

    def select(self, *args, **kwargs):
        self.calls.append(("select", args, kwargs))
        return self

    def insert(self, payload):
        self.calls.append(("insert", payload))
        self.data = [{**payload, "id": "99999999-9999-4999-8999-999999999999"}]
        return self

    def update(self, payload):
        self.calls.append(("update", payload))
        self.data = [{**payload, "id": VEHICLE_ID, "user_id": USER_ID}]
        return self

    def eq(self, column, value):
        self.calls.append(("eq", column, value))
        return self

    def neq(self, column, value):
        self.calls.append(("neq", column, value))
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
        self.calls.append(("execute",))
        return FakeResponse(self.data)


class FakeClient:
    def __init__(self):
        self.queries = []

    def table(self, name):
        query = FakeQuery(name)
        self.queries.append(query)
        return query


class V2RepositoryTests(unittest.TestCase):
    def test_vehicle_reads_are_user_scoped_and_skip_trashed(self):
        client = FakeClient()
        with patch.object(repo, "get_supabase_client", return_value=client):
            repo.list_user_vehicles(user_id=USER_ID)

        calls = client.queries[0].calls
        self.assertIn(("eq", "user_id", USER_ID), calls)
        self.assertIn(("neq", "lifecycle_status", "TRASHED"), calls)

    def test_get_problem_is_user_scoped(self):
        client = FakeClient()
        with patch.object(repo, "get_supabase_client", return_value=client):
            repo.get_problem(user_id=USER_ID, problem_id=PROBLEM_ID)

        calls = client.queries[0].calls
        self.assertIn(("eq", "id", PROBLEM_ID), calls)
        self.assertIn(("eq", "user_id", USER_ID), calls)

    def test_soft_delete_sets_trash_lifecycle_instead_of_delete(self):
        client = FakeClient()
        with patch.object(repo, "get_supabase_client", return_value=client):
            self.assertTrue(repo.soft_delete_vehicle(user_id=USER_ID, vehicle_id=VEHICLE_ID))

        calls = client.queries[0].calls
        update_call = next(call for call in calls if call[0] == "update")
        self.assertEqual(update_call[1]["lifecycle_status"], "TRASHED")
        self.assertIn("trashed_at", update_call[1])
        self.assertIn("restore_until", update_call[1])
        self.assertIn(("eq", "id", VEHICLE_ID), calls)
        self.assertIn(("eq", "user_id", USER_ID), calls)

    def test_source_urls_are_canonicalized_before_insert(self):
        client = FakeClient()
        client.queries = []
        with patch.object(repo, "get_supabase_client", return_value=client):
            source = repo.upsert_source({"title": "Video", "url": "https://youtu.be/abc123?t=5"})

        self.assertEqual(source["canonical_url"], "https://www.youtube.com/watch?v=abc123")


if __name__ == "__main__":
    unittest.main()
