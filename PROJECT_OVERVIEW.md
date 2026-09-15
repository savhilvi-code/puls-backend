# PULS Backend V2 Overview

This repository now represents one backend architecture: Backend Data Core V2.

The source of truth is Supabase V2, centered on users, vehicles, problems, vehicle events, conversations, messages, knowledge, sources, staged search, subscriptions, and payments.

The main interaction layer is conversational. The backend keeps communication history separate from technical vehicle memory. A clean chat can still load a selected vehicle and Problem as structured context for continuing an issue from My Car V2.

External search is not a top-level state. It is a staged research process under a Problem:

Problem -> Search Episode -> Search Run stage 1..N.

Parser/search extraction is preserved as a stage tool, not as the primary conversation engine.

## Active Runtime Modules

- `app/main.py`
- `app/routers/chat.py`
- `app/routers/vehicles.py`
- `app/routers/problems.py`
- `app/routers/history.py`
- `app/routers/search.py`
- `app/routers/health.py`
- `app/services/auth_service.py`
- `app/services/v2_repository.py`
- `app/services/conversation_orchestrator.py`
- `app/services/search_stage_service.py`
- `app/services/parser_service.py`
- `app/services/parser_engine.py`
- `app/services/search_provider.py`
- `app/services/openai_service.py`
- `app/services/subscription_service.py`
- `app/services/vehicle_enrichment_service.py`

## Explicitly Removed

- Legacy diagnostic request persistence.
- Legacy parser-run persistence.
- Old case/history persistence.
- Old solved-case and knowledge-case promotion flow.
- Compatibility history journal.
- Top-level parser/search endpoints.
- Support intake from the backend data core.
