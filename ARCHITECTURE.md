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
