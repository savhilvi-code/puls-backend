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
