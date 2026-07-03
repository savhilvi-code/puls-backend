# Architecture

## Краткое описание

PULS backend - FastAPI-сервис для автомобильной диагностики. Он принимает запросы с сайта, маршрутизирует их через routers, вызывает services для диалога, поиска, парсера и базы знаний, а затем возвращает структурированный ответ клиенту.

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
  - schemas/
    - __init__.py
    - chat.py
    - parser.py
    - router.py
    - user.py
  - services/
    - __init__.py
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

## Services

- `app/services/__init__.py`
- `app/services/dialog_state_service.py`
- `app/services/formatter_service.py`
- `app/services/kb_service.py`
- `app/services/normalize_service.py`
- `app/services/openai_service.py`
- `app/services/parser_engine.py`
- `app/services/parser_service.py`
- `app/services/puls_data_service.py`
- `app/services/request_journal_service.py`
- `app/services/router_service.py`
- `app/services/user_service.py`

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
- `app/routers/chat.py` -> `app/schemas/chat.py`
- `app/routers/chat.py` -> `app/services/dialog_state_service.py`
- `app/routers/chat.py` -> `app/services/formatter_service.py`
- `app/routers/chat.py` -> `app/services/kb_service.py`
- `app/routers/chat.py` -> `app/services/normalize_service.py`
- `app/routers/chat.py` -> `app/services/parser_service.py`
- `app/routers/chat.py` -> `app/services/router_service.py`
- `app/routers/chat.py` -> `app/services/user_service.py`
- `app/routers/history.py` -> `app/services/request_journal_service.py`
- `app/routers/search.py` -> `app/schemas/parser.py`
- `app/routers/search.py` -> `app/services/parser_service.py`
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
- `app/services/kb_service.py`: `knowledge_cases`
- `app/services/request_journal_service.py`: `diagnostic_requests`, `users`
- `app/services/puls_data_service.py`: `conversations`, `messages`, `diagnostic_requests`, `parser_runs`, `video_library`, `user_feedback`, `solved_cases`
- `db/puls_integration.sql`: `conversations`, `messages`, `parser_runs`, `user_feedback`, `solved_cases`, `video_library`, `vehicle_service_logs`
- Telegram transport removed: backend is web/API-only.

## Поток запроса

```mermaid
flowchart LR
    Frontend[Frontend] --> FastAPI[FastAPI]
    FastAPI --> Routers[Routers]
    Routers --> Services[Services]
    Services --> ParserKB[Parser / KB]
    ParserKB --> Supabase[Supabase]
    Supabase --> Response[Response]
```
