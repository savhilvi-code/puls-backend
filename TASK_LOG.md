# Task Log

## 2026-09-16 — stabilization Phase A

- Reproduced authenticated production `POST /api/vehicles` returning HTTP 500, with no created vehicle. Confirmed through read-only PostgREST column checks that the route forwarded nonexistent `fuel`, `drive`, `country`, `city`, `notes` columns. Current repository already mapped brand/engine; the remaining route payload was stale.
- Map vehicle writes to canonical make/engine_code/fuel_type/drivetrain and split the compatibility VIN/frame input. Keep canonical fields and legacy response aliases for the current frontend. Supabase schema unchanged.
- Added focused payload/response/identity tests (3 pass). Existing repository tests have three unrelated stale expectations against the latest upstream repository implementation; security tests pass. Production verification follows deployment.

## Backend Data Core V2

- Rebuilt chat orchestration around structured context and Supabase V2 repositories.
- Added vehicle/problem/event APIs for My Car V2 data needs.
- Added staged research episodes and search runs.
- Moved quota semantics to `subscriptions.quota_limit` and `subscriptions.quota_used`.
- Replaced normal vehicle deletion with soft delete and restore.
- Removed legacy diagnostic request, parser-run, case/history, and old knowledge persistence services.
- Removed stale public docs that described the old architecture.
