# Task Log

## 2026-09-16 — stabilization Phase A

- Reproduced authenticated production `POST /api/vehicles` returning HTTP 500, with no created vehicle. Confirmed through read-only PostgREST column checks that the route forwarded nonexistent `fuel`, `drive`, `country`, `city`, `notes` columns. Current repository already mapped brand/engine; the remaining route payload was stale.
- Map vehicle writes to canonical make/engine_code/fuel_type/drivetrain and split the compatibility VIN/frame input. Keep canonical fields and legacy response aliases for the current frontend. Supabase schema unchanged.
- Added focused payload/response/identity tests (3 pass). Existing repository tests have three unrelated stale expectations against the latest upstream repository implementation; security tests pass. Production verified: authenticated POST/PUT 200 for labeled manual and frame test vehicles, real UUIDs and owner confirmed directly in public.vehicles, one row per test, Admin count 2. Browser F5 and logout/login retain both vehicles; failed validation preserves the draft. On resumption the original test records had been trashed externally, so a separate labeled specification test was used; API and database re-read confirmed actual_value persistence. Frontend checkpoint cd591c9 adapts parameter rows for editing.

## Backend Data Core V2

- Rebuilt chat orchestration around structured context and Supabase V2 repositories.
- Added vehicle/problem/event APIs for My Car V2 data needs.
- Added staged research episodes and search runs.
- Moved quota semantics to `subscriptions.quota_limit` and `subscriptions.quota_used`.
- Replaced normal vehicle deletion with soft delete and restore.
- Removed legacy diagnostic request, parser-run, case/history, and old knowledge persistence services.
- Removed stale public docs that described the old architecture.

## 2026-09-17 — Phase B chat contract

- Production history already persisted USER/ASSISTANT content, but frontend lowercase-only filtering discarded it. /chat omitted identity, breaking follow-up resolution.
- Return authoritative conversation/vehicle/problem IDs; history supplies scope and selects by last_message_at. Expired supplied session IDs no longer reuse raw context; raw rows remain untouched. Frontend normalizes canonical roles/content and restores latest backend history without depending on a local marker.
- Chat stabilization/security tests: 9 passed. Frontend regression passed against uppercase content fixtures. Production verification: two authenticated /chat calls returned the same conversation UUID and four raw messages were read from public.messages. Fresh authentication /api/history selected that same conversation without a local marker. Browser F5, Settings and My Car navigation restored it; logout cleared private bubbles. Boundary tests verify >=12h clean context without deletions; the test account currently has no >12h messages, so no historical timestamps were altered.

## 2026-09-17 — C1 initial quota reproduction (not yet corrected)

- Created one explicitly labeled signup test account. Before any authenticated backend request for that account, Admin reported free / quota_limit 3 / quota_used 0. Signup created the subscription; backend provisioning is not the source of 3 (FREE_LIMIT is already 5 and existing database limits are preserved).
- Signup requires email confirmation, so no user session was issued. Production trigger/default definitions are not present locally or exposed by the available API. Read-only SQL inspection is prepared locally; Dashboard access requested before changing the actual source. No production schema/data correction attempted, and no historical accounts rewritten.
- Corrected a stale test expectation of default 10 to canonical 5; added coverage that existing custom limits are not silently rewritten. All 5 subscription tests pass. Remaining C items wait for C1 in the requested order.
