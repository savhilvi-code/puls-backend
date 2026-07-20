# Architecture

## Краткое описание

PULS backend - FastAPI-сервис для автомобильной диагностики. Он принимает запросы с сайта, маршрутизирует их через routers, вызывает services для диалога, поиска, парсера и базы знаний, а затем возвращает структурированный ответ клиенту.

`app/services/decision_engine.py` является единым центром принятия решений для `/chat`: он определяет автомобиль и контекст, проверяет `knowledge_cases` и историю, решает запускать ли Parser или Deep Search, следит за quota-safe ответами и передает результат в persistence-слой.

## Структура папок

```text
- app/
  - __init__.py
  - database/
    - __init__.py
    - supabase.py
  - main.py
  - routers/
    - __init__.py
    - chat.py
    - health.py
    - history.py
    - search.py
    - vehicles.py
  - schemas/
    - __init__.py
    - chat.py
    - parser.py
    - router.py
    - user.py
  - services/
    - __init__.py
    - decision_engine.py
    - dialog_state_service.py
    - formatter_service.py
    - kb_service.py
    - normalize_service.py
    - openai_service.py
    - parser_engine.py
    - parser_service.py
    - puls_data_service.py
    - request_journal_service.py
    - router_service.py
    - user_service.py
  - utils/
    - __init__.py
    - formatting.py
    - language.py
```

## Routers

- `app/routers/__init__.py`
- `app/routers/chat.py`
- `app/routers/health.py`
- `app/routers/history.py`
- `app/routers/search.py`
- `app/routers/vehicles.py`

## Vehicle Persistence Notes

- `POST /api/vehicles` now acts as a guarded create path, not a blind insert.
- Backend rejects empty vehicle payloads instead of creating blank `vehicles` rows.
- When the same signed-in user submits the same VIN again, backend reuses the existing `vehicles` row and updates it.
- When VIN is missing, backend falls back to a duplicate signature check on `brand/model/year/engine` so repeated create requests still collapse into one vehicle instead of multiplying records.
- `POST /api/vehicles/enrich` is a draft-only enrichment path: it does not save anything, but it can use the PULS model plus web search to verify remaining vehicle fields and attach a representative car photo URL for the current draft.

## Services

- `app/services/__init__.py`
- `app/services/decision_engine.py`
- `app/services/conversation_service.py`
- `app/services/dialog_state_service.py`
- `app/services/diagnostic_service.py`
- `app/services/feedback_service.py`
- `app/services/formatter_service.py`
- `app/services/kb_service.py`
- `app/services/knowledge_service.py`
- `app/services/media_service.py`
- `app/services/message_service.py`
- `app/services/normalize_service.py`
- `app/services/openai_service.py`
- `app/services/parser_engine.py`
- `app/services/parser_run_service.py`
- `app/services/parser_service.py`
- `app/services/puls_data_service.py`
- `app/services/request_journal_service.py`
- `app/services/router_service.py`
- `app/services/subscription_service.py`
- `app/services/user_service.py`
- `app/services/vehicle_service.py`
- `app/services/vehicle_enrichment_service.py`

## Schemas

- `app/schemas/__init__.py`
- `app/schemas/chat.py`
- `app/schemas/parser.py`
- `app/schemas/router.py`
- `app/schemas/user.py`

## Database Files

- `app/database/__init__.py`
- `app/database/supabase.py`

## Prompts

- `app/prompts/router_prompt.txt`

## Зависимости между файлами

- `app/database/supabase.py` -> `app/schemas/user.py`
- `app/main.py` -> `app/routers/chat.py`
- `app/main.py` -> `app/routers/health.py`
- `app/main.py` -> `app/routers/history.py`
- `app/main.py` -> `app/routers/search.py`
- `app/main.py` -> `app/routers/vehicles.py`
- `app/routers/chat.py` -> `app/schemas/chat.py`
- `app/routers/chat.py` -> `app/services/decision_engine.py`
- `app/routers/history.py` -> `app/services/request_journal_service.py`
- `app/routers/search.py` -> `app/schemas/parser.py`
- `app/routers/search.py` -> `app/services/parser_service.py`
- `app/routers/vehicles.py` -> `app/database/supabase.py`
- `app/routers/vehicles.py` -> `app/services/puls_data_service.py`
- `app/services/decision_engine.py` -> `app/schemas/chat.py`
- `app/services/decision_engine.py` -> `app/services/dialog_state_service.py`
- `app/services/decision_engine.py` -> `app/services/formatter_service.py`
- `app/services/decision_engine.py` -> `app/services/kb_service.py`
- `app/services/decision_engine.py` -> `app/services/normalize_service.py`
- `app/services/decision_engine.py` -> `app/services/parser_service.py`
- `app/services/decision_engine.py` -> `app/services/puls_data_service.py`
- `app/services/decision_engine.py` -> `app/services/router_service.py`
- `app/services/decision_engine.py` -> `app/services/subscription_service.py`
- `app/services/decision_engine.py` -> `app/services/user_service.py`
- `app/services/user_service.py` -> `app/services/conversation_service.py`
- `app/services/user_service.py` -> `app/services/diagnostic_service.py`
- `app/services/user_service.py` -> `app/services/feedback_service.py`
- `app/services/user_service.py` -> `app/services/kb_service.py`
- `app/services/user_service.py` -> `app/services/media_service.py`
- `app/services/user_service.py` -> `app/services/parser_run_service.py`
- `app/services/user_service.py` -> `app/services/subscription_service.py`
- `app/services/dialog_state_service.py` -> `app/schemas/router.py`
- `app/services/dialog_state_service.py` -> `app/schemas/user.py`
- `app/services/kb_service.py` -> `app/database/supabase.py`
- `app/services/kb_service.py` -> `app/services/formatter_service.py`
- `app/services/normalize_service.py` -> `app/schemas/chat.py`
- `app/services/normalize_service.py` -> `app/utils/language.py`
- `app/services/openai_service.py` -> `app/schemas/router.py`
- `app/services/parser_engine.py` -> `app/schemas/parser.py`
- `app/services/parser_service.py` -> `app/schemas/parser.py`
- `app/services/parser_service.py` -> `app/services/parser_engine.py`
- `app/services/puls_data_service.py` -> `app/database/supabase.py`
- `app/services/request_journal_service.py` -> `app/database/supabase.py`
- `app/services/router_service.py` -> `app/schemas/router.py`
- `app/services/router_service.py` -> `app/services/openai_service.py`
- `app/services/router_service.py` -> `app/utils/language.py`
- `app/services/user_service.py` -> `app/database/supabase.py`
- `app/services/user_service.py` -> `app/schemas/user.py`
- `app/services/user_service.py` -> `app/services/dialog_state_service.py`
- `app/services/user_service.py` -> `app/services/request_journal_service.py`
- `app/utils/formatting.py` -> `app/schemas/chat.py`
- `app/utils/formatting.py` -> `app/utils/language.py`

## Таблицы Supabase

- `app/database/supabase.py`: `knowledge_cases`, `users`
- `app/database/supabase.py`: Supabase client now prefers `SUPABASE_SERVICE_ROLE_KEY` over `SUPABASE_KEY` so backend writes can bypass RLS safely.
- `app/services/kb_service.py`: `knowledge_cases`, `solved_cases`
- `app/services/request_journal_service.py`: `conversations`, `messages`, `diagnostic_requests`, `users`
- `app/services/decision_engine.py`: central chat decision flow for vehicle context, knowledge lookup, Parser, Deep Search and quota-safe responses
- `app/services/conversation_service.py`: `conversations`, `messages`
- `app/services/diagnostic_service.py`: `diagnostic_requests`
- `app/services/feedback_service.py`: `user_feedback`
- `app/services/media_service.py`: `media_files`
- `app/services/parser_run_service.py`: `parser_runs`
- `app/services/puls_data_service.py`: `vehicles`, `solved_cases`
- `app/services/subscription_service.py`: `subscriptions`
- `app/routers/vehicles.py`: `/api/vehicles` CRUD for user-owned vehicle cards. Deleting a user vehicle removes the personal card and vehicle service logs, while solved diagnostic cases keep a brand/model/year/engine snapshot for the shared knowledge base.
- `app/routers/vehicles.py`: `/api/vehicles` also round-trips editable technical spec fields (`displacement`, `power`, `torque`, `engine_type`, `cylinders`, `emissions`, `tank`). For simpler live debugging these values are persisted safely through the existing `vehicles.notes` metadata envelope even before the optional explicit SQL columns are applied.
- `app/services/vehicle_enrichment_service.py`: JDM chassis enrichment now supports an additional local fallback provider backed by `data/jdm_chassis_codes.json` before falling through to external provider/API or model-based research.
- `db/puls_production_schema.sql`: canonical production schema for `users`, `subscriptions`, `payments`, `vehicles`, `conversations`, `messages`, `diagnostic_requests`, `parser_runs`, `user_feedback`, `solved_cases`, `knowledge_cases`, `video_library`, `vehicle_service_logs`, `media_files` and related indexes
- Telegram transport removed: backend is web/API-only.

## Supabase Runtime Requirements

- Backend must use `SUPABASE_SERVICE_ROLE_KEY` in Render for write operations.
- `SUPABASE_KEY` may remain for compatibility, but publishable/anon keys cannot insert rows when RLS is enabled.
- `/health` returns Supabase diagnostics: configured, read_ok, service_key, key_source, and a short read error if available.
- Persistence failures are logged by `user_service` and `puls_data_service` instead of being silently hidden.

## Поток запроса

```mermaid
flowchart LR
    Frontend[Frontend] --> FastAPI[FastAPI]
    FastAPI --> Routers[Routers]
    Routers --> Decision[Decision Engine]
    Decision --> Services[Services]
    Services --> ParserKB[Parser / KB]
    ParserKB --> Supabase[Supabase]
    Supabase --> Response[Response]
```

## Vehicle Context Rules

- User-owned cars live in `vehicles` and are exposed through `/api/vehicles`.
- `/chat` receives the active frontend car as `car_info`; Decision Engine first tries to resolve it to the user's `vehicles.id`.
- If the user explicitly mentions another car, the mentioned car overrides the previous active context. If it is not in `vehicles`, it remains a dialog context without creating a personal vehicle row.
- Feedback and follow-up messages reuse the last diagnostic vehicle context. They must not silently rebind to the saved profile car if the solved/requested car was different.
- Active service/consumable dialogs (oil, ATF, coolant, brake fluid, steering fluid) are tracked inside the backend chat state machine. Short clarification replies must keep the original service seed query, vehicle, service target, and subtype until the service flow is finished, and must not fall through into unrelated generic diagnostic fallback.
- Knowledge lookup is vehicle-aware: a case for Nissan/SR20VET must not satisfy a Toyota/1G-GZE request.
- Knowledge lookup checks both `knowledge_cases` and confirmed `solved_cases` before Parser/Deep Search starts.
- Parser history context is filtered by the active vehicle before it is passed to Parser/Deep Search, preventing old-car contamination.
- `solved_cases` keeps vehicle snapshot fields, so successful cases remain useful after a user deletes a personal vehicle card.

## Page To Table Matrix

The current production rule is to keep distinct tables for distinct product surfaces. The problem is not the number of tables; the problem is whether every page reads and writes the correct table with the correct vehicle context.

| Page | Source tables | Backend writer | Frontend reader | Current status |
| --- | --- | --- | --- | --- |
| My Car | `vehicles` | `app/routers/vehicles.py`, `app/services/puls_data_service.py` | `assets/js/app.js` via `/api/vehicles` | Production-backed |
| Service and maintenance block inside My Car | `vehicle_service_logs` | not yet connected in runtime flow | `assets/js/app.js` local draft/localStorage flow | UI exists, backend table not yet wired |
| Request History | `conversations`, `messages`, `diagnostic_requests` | `conversation_service`, `diagnostic_service`, `user_service` | `assets/js/app.js` via `/api/history` | Production-backed |
| Request Journal / solved work cases | `solved_cases` enriched through `/api/history` | `puls_data_service.create_solved_case_from_diagnostic`, `user_service` | `assets/js/app.js` history/journal renderer | Production-backed, vehicle binding must stay strict |
| Shared knowledge base | `knowledge_cases`, `knowledge_events` | `kb_service.save_confirmed_case_to_knowledge` | backend lookup only | Production-backed, promotion must stay vehicle-safe |
| Videos | `video_library` as personal shelf, `media_files` as all found materials | `media_service`, `puls_data_service.save_video_library`, `user_service` | current page still uses static/demo rows | Backend write path exists, frontend reader not yet switched |
| DTC | `dtc_errors` | not yet connected in runtime flow | current page still uses static/demo rows | Demo/UI only for now |
| Manuals | `media_files` or future manuals table/catalog | not yet connected in runtime flow | current page still uses static/demo rows | Demo/UI only for now |
| Parser / Deep Search trace | `parser_runs`, `media_files` | `parser_run_service`, `media_service`, `user_service` | not exposed as dedicated page yet | Production-backed persistence |
| Quota and subscription | `subscriptions`, `payments` | `subscription_service` | `assets/js/app.js` from backend quota payload and settings screen | Production-backed for quota, payments not yet live |

## Persistence Rules

- `vehicles` is the only source of truth for user-owned cars.
- `vehicle_profiles` is a catalog/reference table and must not be used as the storage for user-owned cars.
- `solved_cases` stores only the user's own confirmed completed cases.
- `knowledge_cases` stores only promoted, vehicle-safe, confirmed cases after feedback-based validation.
- `knowledge_events` logs when and why a confirmed case is promoted into the shared knowledge layer.
- `media_files` stores all found links, documents, and materials tied to a diagnostic request.
- `video_library` stores only the personal video subset of the broader `media_files`/search output.
- Pages that are still demo/static must not be described in UI copy as if they already reflect production persistence.
- `app/services/support_service.py`: support intake service for `POST /api/support`; validates uploaded images, stores them in Supabase Storage `support-attachments`, and writes `support_requests` rows for future support analytics and email forwarding.
- `app/routers/support.py`: guest/auth support endpoint for the Settings modal. Accepts `subject`, `message`, editable `email`, optional `auth_user_id`, and up to 3 images.
- `db/support_requests.sql`: bootstrap SQL for the `support_requests` table used by the MVP support flow.
