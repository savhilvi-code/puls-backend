from __future__ import annotations

import asyncio
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import logging
import re
import threading
import time
from typing import Any
from uuid import uuid4

from app.database.supabase import get_supabase_client, rows


logger = logging.getLogger(__name__)
_SENSITIVE = re.compile(r"(^|_)(authorization|cookie|password|secret|api_key|access_token|refresh_token|jwt|credential)($|_)", re.I)
_SECRET_VALUE = re.compile(r"(?:\bBearer\s+[A-Za-z0-9._-]+|\bsk-[A-Za-z0-9_-]+|\bsb_secret_[A-Za-z0-9_-]+)", re.I)
_last_cleanup = 0.0
_cleanup_lock = threading.Lock()


@dataclass
class TraceContext:
    id: str
    request_id: str
    started_at: datetime
    started_monotonic: float
    sequence: int = 0
    fields: dict[str, Any] = field(default_factory=dict)


_current: ContextVar[TraceContext | None] = ContextVar("puls_request_trace", default=None)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _bounded(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return "[truncated]"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in list(value.items())[:30]:
            name = str(key)
            result[name] = "[redacted]" if _SENSITIVE.search(name) else _bounded(item, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple, set)):
        return [_bounded(item, depth=depth + 1) for item in list(value)[:20]]
    if isinstance(value, str):
        clean = _SECRET_VALUE.sub("[redacted]", value)
        return clean[:600] + ("…" if len(clean) > 600 else "")
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:600]


def sanitize(value: Any) -> Any:
    bounded = _bounded(value)
    try:
        encoded = json.dumps(bounded, ensure_ascii=False, default=str)
        if len(encoded) <= 12000:
            return bounded
    except Exception:
        pass
    return {"truncated": True}


def current_trace_id() -> str | None:
    context = _current.get()
    return context.id if context else None


def _cleanup_expired() -> None:
    global _last_cleanup
    now = time.monotonic()
    if now - _last_cleanup < 3600 or not _cleanup_lock.acquire(blocking=False):
        return
    try:
        _last_cleanup = now
        get_supabase_client().table("request_traces").delete().lt("retention_until", _now().isoformat()).execute()
    except Exception:
        logger.debug("Trace retention cleanup failed open", exc_info=True)
    finally:
        _cleanup_lock.release()


def start_trace(*, message: str, source: str) -> Token:
    started = _now()
    context = TraceContext(
        id=str(uuid4()), request_id=str(uuid4()), started_at=started,
        started_monotonic=time.monotonic(),
    )
    token = _current.set(context)
    try:
        get_supabase_client().table("request_traces").insert({
            "id": context.id,
            "request_id": context.request_id,
            "source": str(source or "web")[:32],
            "message_excerpt": str(message or "")[:240],
            "status": "RUNNING",
            "started_at": started.isoformat(),
            "retention_until": (started + timedelta(days=14)).isoformat(),
            "metadata": {},
        }).execute()
        emit_event("REQUEST", operation="CONTEXT", status="STARTED", from_node="USER", to_node="API", edge_label="REQUEST", input_data={"message_excerpt": str(message or "")[:240]})
        _cleanup_expired()
    except Exception:
        logger.debug("Trace creation failed open", exc_info=True)
    return token


def bind_trace(**fields: Any) -> None:
    context = _current.get()
    if not context:
        return
    clean = {key: value for key, value in fields.items() if value is not None}
    context.fields.update(clean)
    try:
        get_supabase_client().table("request_traces").update(sanitize(clean)).eq("id", context.id).execute()
    except Exception:
        logger.debug("Trace binding failed open", exc_info=True)


def emit_event(
    event_type: str, *, module: str = "", operation: str = "", status: str = "COMPLETED",
    from_node: str = "", to_node: str = "", edge_label: str = "", table_name: str | None = None,
    record_id: str | None = None, affected_rows: int | None = None, field_names: list[str] | None = None,
    stage_number: int | None = None, source_group: str | None = None, provider: str | None = None,
    model: str | None = None, duration_ms: int | None = None, related_ids: dict[str, Any] | None = None,
    input_data: Any = None, output_data: Any = None, telemetry: Any = None,
) -> dict[str, Any] | None:
    context = _current.get()
    if not context:
        return None
    context.sequence += 1
    payload = {
        "trace_id": context.id, "sequence": context.sequence, "occurred_at": _now().isoformat(),
        "offset_ms": max(0, int((time.monotonic() - context.started_monotonic) * 1000)),
        "event_type": str(event_type)[:64], "module": str(module)[:96],
        "operation": str(operation)[:32], "status": str(status)[:32],
        "from_node": str(from_node)[:100], "to_node": str(to_node)[:100], "edge_label": str(edge_label or operation)[:100],
        "table_name": table_name, "record_id": str(record_id) if record_id else None,
        "affected_rows": affected_rows, "field_names": list(field_names or [])[:30],
        "stage_number": stage_number, "source_group": source_group, "provider": provider, "model": model,
        "duration_ms": duration_ms, "related_ids": sanitize(related_ids or {}),
        "input_data": sanitize(input_data or {}), "output_data": sanitize(output_data or {}),
        "telemetry": sanitize(telemetry or {}),
    }
    payload = {key: value for key, value in payload.items() if value is not None}
    try:
        get_supabase_client().table("trace_events").insert(payload).execute()
    except Exception:
        logger.debug("Trace event failed open", exc_info=True)
    return payload


def finish_trace(*, status: str, response: Any = None, error_code: str | None = None, token: Token | None = None) -> None:
    context = _current.get()
    if not context:
        return
    duration = max(0, int((time.monotonic() - context.started_monotonic) * 1000))
    emit_event("ANSWER", operation="RESULT", status=status, from_node="API", to_node="USER", edge_label="ANSWER", duration_ms=duration, output_data=response or {})
    try:
        get_supabase_client().table("request_traces").update({
            "status": status, "completed_at": _now().isoformat(), "duration_ms": duration,
            "event_count": context.sequence, "error_code": error_code,
        }).eq("id", context.id).execute()
    except Exception:
        logger.debug("Trace completion failed open", exc_info=True)
    finally:
        if token is not None:
            _current.reset(token)


def list_traces(*, limit: int = 50, status: str | None = None, user_id: str | None = None, vehicle_id: str | None = None, intent: str | None = None) -> list[dict[str, Any]]:
    query = get_supabase_client().table("request_traces").select("*").order("started_at", desc=True).limit(max(1, min(limit, 100)))
    for name, value in (("status", status), ("user_id", user_id), ("vehicle_id", vehicle_id), ("intent", intent)):
        if value:
            query = query.eq(name, value)
    return rows(query.execute())


def get_trace(trace_id: str) -> dict[str, Any] | None:
    found = rows(get_supabase_client().table("request_traces").select("*").eq("id", trace_id).limit(1).execute())
    if not found:
        return None
    found[0]["events"] = list_events(trace_id)
    return found[0]


def list_events(trace_id: str, after_sequence: int = 0) -> list[dict[str, Any]]:
    query = get_supabase_client().table("trace_events").select("*").eq("trace_id", trace_id).gt("sequence", after_sequence).order("sequence")
    return rows(query.execute())


async def event_stream(trace_id: str, request: Any, after_sequence: int = 0):
    cursor = after_sequence
    while not await request.is_disconnected():
        try:
            events = await asyncio.to_thread(list_events, trace_id, cursor)
            for event in events:
                cursor = max(cursor, int(event.get("sequence") or 0))
                yield f"event: trace\ndata: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
            state = rows((await asyncio.to_thread(lambda: get_supabase_client().table("request_traces").select("status").eq("id", trace_id).limit(1).execute())))
            status = str((state[0] if state else {}).get("status") or "")
            if status and status != "RUNNING" and not events:
                yield f"event: complete\ndata: {json.dumps({'status': status})}\n\n"
                break
            if not events:
                yield ": heartbeat\n\n"
        except Exception:
            yield "event: warning\ndata: {\"status\":\"unavailable\"}\n\n"
        await asyncio.sleep(0.75)
