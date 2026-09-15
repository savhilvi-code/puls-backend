# PULS Backend V2

FastAPI backend for the PULS automotive assistant.

Backend V2 is built around the Supabase V2 domain model:

- users
- subscriptions and payments
- vehicles and vehicle_specs
- conversations and messages
- problems and vehicle_events
- knowledge_items and sources
- search_episodes and search_runs

Chat remains natural by default. Stored vehicles and active technical Problems are structured context, not a reason to turn every short message into diagnostics.

## Local Run

1. Copy `.env.example` to `.env`.
2. Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` for persistence.
3. Set `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY` for AI-backed chat/search.
4. Install dependencies.
5. Start the API:

```powershell
uvicorn app.main:app --reload
```

## Notes

- The production Supabase schema is authoritative.
- The backend never uses a client-provided `user_id` for ownership-sensitive operations.
- Search quota is stored in `subscriptions.quota_limit` and `subscriptions.quota_used`.
- External research runs as Search Episode -> Search Run stage 1..N.
- Raw chat history is communication history, not the vehicle's technical memory.
