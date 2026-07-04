# Task Log

## 2026-07-03

- Создана система документации для Codex.
- Добавлены ARCHITECTURE.md, CODEX_RULES.md, TASK_LOG.md.
- Добавлен scripts/generate_architecture.py для обновления карты проекта.
- Удален Telegram-транспорт из backend: убраны router/service, поля telegram_id/chat_id из входных схем, user-схем и Supabase user lookup.
- Обновлены PROJECT_OVERVIEW.md и ARCHITECTURE.md под web-only поток без Telegram.
- Добавлен db/remove_telegram.sql для очистки Telegram-only данных и удаления telegram_id из существующей Supabase.
- Добавлен db/puls_integration.sql для web-first интеграции Supabase: conversations, messages, parser_runs, user_feedback, solved_cases, video_library, vehicle_service_logs и недостающие поля лимитов.
- ChatResponse расширен полем quota, бесплатный лимит Parser/Deep Search установлен на 10 запросов.
- Добавлен app/services/puls_data_service.py: backend теперь создает активные conversations, пишет messages, diagnostic_requests, parser_runs, video_library, user_feedback и solved_cases.
- Исправлено списание лимита: kb_match больше не расходует Parser/Deep Search лимит.
- Добавлен db/clean_test_data.sql для ручной очистки тестовой Supabase: удаляет пользователей, связанные user-owned данные и содержит проверочные запросы на пустую users и orphan-записи.
- Добавлен app/services/decision_engine.py как единый PULS Decision Engine: `/chat` стал тонким router-слоем, а backend централизованно решает vehicle context, knowledge_cases/history lookup, Parser, Deep Search, quota и feedback flow.
- Расширен app/services/puls_data_service.py: добавлены поиск автомобиля пользователя, поиск последнего диагностического запроса и создание solved_case из последнего успешного диагностического ответа.
- 2026-07-04: Diagnosed empty Supabase writes. The current backend key is publishable/anon and fails inserts under RLS. Backend now prefers `SUPABASE_SERVICE_ROLE_KEY`, `/health` exposes Supabase diagnostics, and persistence/parser failures are logged for Render troubleshooting.
- 2026-07-04: Extended Supabase secret-key detection to support `SUPABASE_SECRET_KEY` and `SUPABASE_SERVICE_KEY`; `/health` now reports Supabase env variable names without exposing values.
- 2026-07-04: Added `/health.supabase.service_role_present` to explicitly confirm whether Render exposes `SUPABASE_SERVICE_ROLE_KEY` to the running backend.
- 2026-07-04: Fixed feedback classification so `not helped` is stored as `not_helped`, and normalized embedded JSON from Parser/Deep Search before formatting answers.
- 2026-07-04: Added knowledge/history answer sanitizing so old saved cases with embedded JSON are cleaned before being returned from the internal knowledge base.
- 2026-07-04: Strengthened knowledge answer sanitizing with JSON-like fallback extraction for old malformed cases that cannot be parsed as strict JSON.
- 2026-07-04: Applied knowledge answer cleanup inside Decision Engine KB-match response path to prevent old malformed knowledge cases from reaching chat output.
