from __future__ import annotations

import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.routers import admin
from app.services import trace_service


class FakeQuery:
    def __init__(self, store: dict[str, list[dict]], table: str):
        self.store, self.table, self.action, self.payload = store, table, "select", None
        self.filters: list[tuple[str, str, object]] = []

    def insert(self, payload): self.action, self.payload = "insert", payload; return self
    def update(self, payload): self.action, self.payload = "update", payload; return self
    def delete(self): self.action = "delete"; return self
    def select(self, *_): self.action = "select"; return self
    def eq(self, key, value): self.filters.append(("eq", key, value)); return self
    def gt(self, key, value): self.filters.append(("gt", key, value)); return self
    def lt(self, key, value): self.filters.append(("lt", key, value)); return self
    def order(self, *_args, **_kwargs): return self
    def limit(self, *_): return self

    def execute(self):
        records = self.store.setdefault(self.table, [])
        if self.action == "insert":
            record = dict(self.payload); records.append(record); return SimpleNamespace(data=[record])
        matching = [row for row in records if all((str(row.get(key)) == str(value) if op == "eq" else int(row.get(key, 0)) > int(value) if op == "gt" else True) for op, key, value in self.filters)]
        if self.action == "update":
            for row in matching: row.update(self.payload)
        return SimpleNamespace(data=[dict(row) for row in matching])


class FakeClient:
    def __init__(self): self.store: dict[str, list[dict]] = {}
    def table(self, name): return FakeQuery(self.store, name)


class TraceServiceTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.client_patch = patch.object(trace_service, "get_supabase_client", return_value=self.client)
        self.client_patch.start()
        trace_service._last_cleanup = trace_service.time.monotonic()

    def tearDown(self):
        self.client_patch.stop()

    def test_trace_id_order_database_events_and_redaction(self):
        token = trace_service.start_trace(message="hello", source="web")
        trace_id = trace_service.current_trace_id()
        trace_service.emit_event("DATABASE", operation="READ", from_node="vehicles", to_node="Context", table_name="vehicles", input_data={"authorization": "Bearer secret", "safe": "ok", "note": "token sk-never-expose"})
        trace_service.emit_event("DATABASE", operation="WRITE", from_node="Fact", to_node="vehicle_specs", table_name="vehicle_specs")
        trace_service.emit_event("DATABASE", operation="VERIFY", from_node="vehicle_specs", to_node="Fact", output_data={"verified": True})
        trace_service.finish_trace(status="COMPLETED", token=token)
        events = self.client.store["trace_events"]
        self.assertTrue(trace_id and all(event["trace_id"] == trace_id for event in events))
        self.assertEqual([event["sequence"] for event in events], list(range(1, len(events) + 1)))
        self.assertEqual(events[1]["input_data"], {"authorization": "[redacted]", "safe": "ok", "note": "token [redacted]"})
        self.assertEqual([event["operation"] for event in events[1:4]], ["READ", "WRITE", "VERIFY"])

    def test_concurrent_trace_contexts_are_isolated(self):
        async def worker(label):
            token = trace_service.start_trace(message=label, source="test")
            own = trace_service.current_trace_id()
            await asyncio.sleep(0)
            trace_service.emit_event("RESULT", output_data={"label": label})
            trace_service.finish_trace(status="COMPLETED", token=token)
            return own
        first, second = asyncio.run(self._gather(worker))
        self.assertNotEqual(first, second)
        self.assertEqual({event["trace_id"] for event in self.client.store["trace_events"]}, {first, second})

    async def _gather(self, worker):
        return await asyncio.gather(worker("a"), worker("b"))

    def test_compact_source_stage_and_image_events(self):
        token = trace_service.start_trace(message="search", source="test")
        trace_service.emit_event("KNOWLEDGE", operation="READ", edge_label="MISS")
        trace_service.emit_event("SEARCH_STAGE", operation="SEARCH", stage_number=4, source_group="forums")
        trace_service.emit_event("SOURCE", operation="RESULT", output_data={"url": "https://example.test"})
        trace_service.emit_event("IMAGE", operation="VERIFY", status="SKIPPED", output_data={"reason": "branding_asset"})
        trace_service.finish_trace(status="COMPLETED", token=token)
        events = self.client.store["trace_events"]
        self.assertTrue(any(event.get("stage_number") == 4 and event.get("source_group") == "forums" for event in events))
        self.assertTrue(any(event["event_type"] == "IMAGE" and event["status"] == "SKIPPED" for event in events))

    def test_fail_open_when_observability_storage_fails(self):
        class Broken:
            def table(self, _name): raise RuntimeError("observability unavailable")
        with patch.object(trace_service, "get_supabase_client", return_value=Broken()):
            token = trace_service.start_trace(message="still works", source="test")
            trace_service.emit_event("DATABASE", operation="READ")
            trace_service.finish_trace(status="COMPLETED", token=token)

    def test_admin_endpoints_require_admin_and_sse_is_read_only(self):
        request = object()
        with patch.object(admin, "require_admin", return_value="admin-id") as require, patch.object(admin, "list_traces", return_value=[{"id": "t1"}]):
            result = asyncio.run(admin.admin_live_flow_traces(request))
        self.assertEqual(result["items"][0]["id"], "t1")
        require.assert_called_once_with(request)

        async def fake_stream(*_args, **_kwargs):
            yield "event: complete\ndata: {}\n\n"
        with patch.object(admin, "require_admin", return_value="admin-id") as require, patch.object(admin, "event_stream", fake_stream):
            response = asyncio.run(admin.admin_live_flow_stream(request, "t1", 0))
        self.assertEqual(response.media_type, "text/event-stream")
        require.assert_called_once_with(request)


if __name__ == "__main__":
    unittest.main()
