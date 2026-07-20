# PULS Backend

Production backend for the PULS automotive diagnostics platform.

PULS Backend powers the live application at [pulscar.co](https://pulscar.co) and provides the server-side foundation for conversational vehicle diagnostics, vehicle-aware context handling, request history, support intake, and validated repair case accumulation.

## Technology

- FastAPI
- Python
- Supabase / PostgreSQL
- OpenAI models

## MVP Capabilities

- conversational automotive diagnostics
- vehicle context
- diagnostic history
- validated repair case accumulation
- parser and deep-search integration
- support requests

## Live Product

- Website: [https://pulscar.co](https://pulscar.co)

## Local Run

1. Copy `.env.example` to a local `.env`.
2. Fill in the required environment variables for your local environment.
3. Install dependencies from `requirements.txt`.
4. Start the API:

```powershell
uvicorn app.main:app --reload
```

## Notes

- This repository contains the production backend for the public PULS web application.
- Public documentation is intentionally high level and does not describe internal operational rules or private implementation details.
