# Task Log

## 2026-09-17 — Admin Knowledge Base Data Inspector V1

- Added authenticated, read-only `/admin/knowledge/*` endpoints over the existing canonical V2 tables. List endpoints are bounded and paginated; messages load by expanded conversation, search runs load by expanded episode, and Problem Trace resolves only existing relations.
- Kept `admin_accounts` as the authorization authority and kept all browser access behind the backend service-role client. No Supabase schema, conversation lifecycle, search execution, parser, or Intelligence behavior changed.
- Added focused coverage that every Data Inspector route is GET-only, admin authorization runs before reads, child data is scoped to its parent, and page sizes are bounded.

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

## 2026-09-17 — C1 guarded production migration prepared

- User inspected the live registration trigger: auth.users.on_auth_user_created calls public.handle_new_auth_user(), whose subscriptions INSERT explicitly sets free/active/3/0. This confirms the exact source independently of backend FREE_LIMIT=5.
- Added db/migrations/20260917_free_signup_quota_5.sql. It reads the live complete definition, validates the named trigger and the exact supplied INSERT shape, replaces only the quota literal with 5, and reads back the definition. It preserves registration/profile logic, function attributes, ownership/grants, and existing subscription rows. Unexpected/ambiguous definitions fail closed; already-5 is a no-op.
- Static substitution checks passed for the supplied SQL shape, untouched profile/security text, and changed-column rejection; 5 subscription tests passed; git diff --check passed. No local PostgreSQL runtime is available, so the DO block has not been executed against PostgreSQL here.
- NOT applied to production. Production verification is pending application and a distinct new confirmed test signup (free, quota_limit=5, quota_used=0), followed by backend/Header/Settings/Admin checks. The earlier 3/0 test account must remain unchanged. C2 onward remains pending in the required order.

## 2026-09-17 — Stabilization Block 2 language root cause

- The V2 conversation orchestrator reads `payload.language` directly and defaults it to `en`; it does not call the existing message-language detector. The web frontend always supplies its interface locale, so an English/default UI forces Russian user text to be persisted and answered as English. That same incorrect value flows into `messages.language`, natural-response prompting, localized fallbacks, and diagnostic formatting. Latin technical terms are not the actual deciding signal because the message text is currently bypassed entirely.
- Fixed at that backend boundary: dominant message language now controls the user row and normal response language; Latin vehicle/diagnostic identifiers do not count as English prose; token-only turns fall back to the active conversation language; explicit switch requests affect only the assistant response language. Focused language/orchestrator tests: 11 passed. No frontend, schema, lifecycle, search/parser, problem, vehicle-event, source, My Car, subscription, or quota changes.
