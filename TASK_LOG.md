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
- 2026-07-05: Added backend `/api/vehicles` CRUD for user-owned vehicle cards and connected it to Supabase `vehicles`.
- 2026-07-05: Hardened Decision Engine vehicle context so explicitly mentioned cars override the previous context, history passed to Parser is filtered by active vehicle, and Toyota/1G-GZE requests cannot match old Nissan/SR20VET knowledge.
- 2026-07-05: Changed feedback persistence so `helped/not helped` messages are stored in `user_feedback` and do not become separate diagnostic request questions; Deep Search rows keep the original symptom.
- 2026-07-05: Saved brand/model/year/engine snapshots into `solved_cases` so shared successful cases remain useful after a user deletes a personal vehicle card.
- 2026-07-05: Cleaned history output by trimming malformed embedded JSON/citations and returning readable vehicle labels instead of raw `vehicle_id` values.
- 2026-07-06: Tightened parser answer sanitizing for component-specific searches. Backend now rejects embedded JSON / search-trace text as `parser_summary`, keeps turbo-focused link filtering, and Decision Engine formats structured parser results even when the raw summary is blank so replies do not fall back to generic warm-engine diagnostics.
- 2026-07-06: Reworked backend persistence around `subscriptions`, `conversations/messages`, `diagnostic_requests`, `parser_runs`, `user_feedback`, `solved_cases` and `media_files`. `/chat` no longer spends quota from `users.requests_left`, no longer persists runtime chat state in `users.car_info` / `users.conversation_history`, creates `knowledge_cases` only after confirmed `helped`, and keeps explicit "other car" requests detached from the saved profile vehicle.
- 2026-07-06: Fixed cross-car persistence for feedback and shared knowledge. Follow-up/helped messages now keep the last diagnostic car context instead of rebinding to the profile vehicle, `diagnostic_requests` persist `brand/model/year/engine` snapshots, and knowledge lookup now searches both `knowledge_cases` and confirmed `solved_cases` before spending parser quota.
- 2026-07-17: Connected the active "My car" frontend flow to backend `/api/vehicles` so saved vehicles and `photo_url` persist in Supabase instead of living only in localStorage. The car photo card now hides the attach label after upload, shows a dropdown for replace/delete actions, clears local service records when a vehicle is removed, and keeps the new UI strings translated for both Russian and English.
- 2026-07-17: Extended backend vehicle payloads so technical specification fields (displacement, power, torque, engine type, cylinders, emissions, tank) round-trip through `/api/vehicles`. For simpler live debugging, spec values are persisted safely through the existing `vehicles.notes` metadata envelope even before the optional SQL schema update is applied.
- 2026-07-17: Updated `db/schema.sql`, `db/puls_integration.sql`, and `db/puls_supabase_alignment.sql` with optional explicit `vehicles` columns for technical specs so the database structure can be normalized later without changing the frontend flow.
- 2026-07-17: Hardened backend `/api/vehicles` create logic for the debug flow. Empty vehicle creates are now rejected with `400`, repeated `POST` calls with the same VIN reuse the existing vehicle instead of inserting a duplicate, and repeated creates with the same `brand/model/year/engine` signature also collapse into a single vehicle row for that user.
- 2026-07-17: Added backend `POST /api/vehicles/enrich` plus `app/services/vehicle_enrichment_service.py`. PULS can now use the model with web search to verify missing vehicle fields, normalize the result into the current car draft, and attach a representative car photo URL by VIN or by `brand/model/year` query before the user explicitly saves the vehicle.
- 2026-07-18: Reverted the later experimental VIN/JDM lookup changes after they degraded stable decoding for existing cars. Backend was returned to the post-`77ac448` state and the live frontend VIN flow was restored to the earlier baseline before adding a new provider.
- 2026-07-18: Started a safer vehicle lookup plan based on a free/open cascade instead of free-form generation. The new direction uses local JDM chassis dictionaries, confirmed PULS vehicle data, free VIN decoding, local WMI decoding, and optional open web search with explicit confidence levels rather than paid VIN APIs.
- 2026-07-18: Added a dedicated `vehicle_lookup_service` and backend `/api/vehicles/lookup` route. VIN and JDM chassis detection now normalize identifiers, separate 17-character VIN lookup from Japanese chassis lookup, track confidence/source/user confirmation in vehicle metadata, and keep ambiguous results as user-choice drafts instead of auto-saving them.
