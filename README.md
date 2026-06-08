# PULS car diagnostic backend

FastAPI scaffold extracted from the n8n workflow export.
The parser/search API is now embedded in this backend, so the project is split into two repos:
`puls-backend` and `cardiagnostic-ai`.

## Run

1. Create `.env` from `.env.example` and fill the values.
2. Install Python dependencies from `requirements.txt`.
3. Start the API:

```powershell
uvicorn app.main:app --reload
```

## Render

This project includes `render.yaml` for a Python web service. On Render, use the provided environment variables from `.env.example`, including `FRONTEND_API_URL=/chat` for the frontend integration point.

## Structure

- `app/main.py` - FastAPI app entrypoint.
- `app/routers/chat.py` - `POST /chat` orchestration.
- `app/routers/telegram.py` - `POST /telegram/webhook`.
- `app/routers/health.py` - `GET /health`.
- `app/services/normalize_service.py` - input normalization from web and Telegram.
- `app/services/router_service.py` - message classification.
- `app/services/user_service.py` - user lookup/update flow.
- `app/services/kb_service.py` - knowledge base lookup/save stub.
- `app/services/parser_engine.py` - embedded parser/search service.
- `app/services/parser_service.py` - local adapter used by `/chat`.
- `app/routers/search.py` - `/search` and `/diagnose` endpoints backed by the embedded parser.
- `app/services/openai_service.py` - OpenAI integration placeholder.
- `app/services/telegram_service.py` - Telegram Bot API sender.
- `app/database/supabase.py` - Supabase client and repository layer.
- `app/schemas/*` - Pydantic models.
- `app/utils/*` - language and formatting helpers.
- `app/prompts/router_prompt.txt` - router prompt copied from the workflow.

## Notes

This project keeps the main orchestration in FastAPI while preserving the parser/search flow from the old API service inside the same backend.
