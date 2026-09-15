# Task Log

## Backend Data Core V2

- Rebuilt chat orchestration around structured context and Supabase V2 repositories.
- Added vehicle/problem/event APIs for My Car V2 data needs.
- Added staged research episodes and search runs.
- Moved quota semantics to `subscriptions.quota_limit` and `subscriptions.quota_used`.
- Replaced normal vehicle deletion with soft delete and restore.
- Removed legacy diagnostic request, parser-run, case/history, and old knowledge persistence services.
- Removed stale public docs that described the old architecture.
