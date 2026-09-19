# Backend V2 Architecture

## Boundaries

The backend is organized around:

- `app/routers`: API surface.
- `app/services/auth_service.py`: Supabase Auth/profile resolution.
- `app/services/v2_repository.py`: Supabase V2 data access and ownership filters.
- `app/services/conversation_orchestrator.py`: chat/context orchestration.
- `app/services/search_stage_service.py`: staged research episodes and runs.
- `app/services/parser_service.py`: parser/search extraction as an internal stage tool.
- `app/services/openai_service.py` and `app/services/search_provider.py`: AI integrations.

## Runtime Flow

`/chat` resolves the authenticated profile, stores messages as communication, loads relevant structured context, and classifies the current turn.

General conversation and meta-chat stay lightweight. A saved vehicle is silent unless the current turn is about it.

Diagnostic turns resolve a vehicle and an active Problem. If critical context is missing, PULS asks one clarification question and stops. When context is sufficient, PULS checks internal structured knowledge first. External research starts only when more evidence is needed.

## Persistence Model

Communication:

- `conversations`
- `messages`

Technical vehicle memory:

- `vehicles`
- `vehicle_specs`
- `problems`
- `vehicle_events`

Research evidence:

- `search_episodes`
- `search_runs`
- `sources`
- `problem_sources`
- `knowledge_items`
- `knowledge_sources`

Fleet experience:

- `fleet_events`

Billing:

- `subscriptions`
- `payments`

## Search Stages

A Problem owns a `search_episode`. Each research stage creates one `search_run` with `stage_number`, input context, result data, source lists, sufficiency, and next-stage reason.

Stage count is not hard-coded to two. Each later stage receives previous-stage summaries and avoids repeating the same evidence without reason. If evidence is sufficient, research stops and quota is consumed once for the episode.

## Security

The backend uses Supabase Auth as identity foundation and `public.users` as the app profile. Route handlers resolve ownership server-side. Normal clients cannot modify payments or subscription entitlements.

The Supabase service-role key is server-only and read from server environment variables. Publishable Supabase keys are not accepted for backend server writes.

## Admin Data Inspector

`/admin/knowledge/*` is a read-only observability API for canonical V2 data. Every route reuses `admin_accounts` authorization. Parent lists are paginated; conversation messages, search runs, and Problem Trace are loaded through parent-scoped endpoints so the browser never queries privileged Supabase tables directly or downloads the full dataset at startup.

Dashboard counts and distributions are calculated independently so one unavailable table or auxiliary relation does not hide otherwise readable canonical data. Unavailable metrics are returned as `null` with an error map; the frontend must distinguish that state from a real zero.

## Admin Knowledge Library

`/admin/knowledge/library/*` is the admin-only management API for the existing global knowledge layer. It reuses `vehicle_configurations` for applicability, `knowledge_items` for structured knowledge and review status, `sources` plus `knowledge_sources` for provenance, and confirmed `fleet_events` as successful-case review candidates. General knowledge keeps a null `vehicle_configuration_id`.

Mechanic review is stored separately from the preserved original-case snapshot in knowledge metadata. Archive is a recoverable metadata lifecycle marker; hard delete is exposed only through the separate preview-and-confirm admin flow. The browser never receives service-role credentials, filtering and pagination remain server-side, and this interface does not alter chat, Search, Problems, Fleet promotion, or provider execution.

Admin hard-delete endpoints are separate from Archive and require a fresh delete preview. Vehicle deletion follows the verified production FK rules: specs, Problems, Search descendants and vehicle events cascade; conversations and Fleet origin links detach; shared vehicle configurations, Fleet knowledge, Sources and Storage objects are preserved. Deleting a Successful Case also deletes its promoted Knowledge Items and their relation rows, while deleting a Knowledge Material deletes only that item and its relations. Canonical Sources are never deleted by these operations.
