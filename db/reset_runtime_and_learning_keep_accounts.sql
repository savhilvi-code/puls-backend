-- Reset learned/runtime PULS data while keeping account, subscription, payment,
-- and vehicle profile records intact.
--
-- Recommended when:
-- - answers are polluted by stale conversations or bad promoted knowledge
-- - you want to keep users, requests quotas, subscriptions, and saved vehicles
--
-- Run manually in Supabase SQL Editor with owner/service privileges.

begin;

-- Shared learning/event data first.
delete from public.knowledge_events;
delete from public.knowledge_cases;

-- User-facing runtime data.
delete from public.parser_runs;
delete from public.user_feedback;
delete from public.solved_cases;
delete from public.video_library;
delete from public.media_files;
delete from public.messages;
delete from public.conversations;
delete from public.diagnostic_requests;
delete from public.dtc_errors;
delete from public.vehicle_service_logs;

commit;

-- Verification summary.
select 'knowledge_events' as table_name, count(*) as rows_count from public.knowledge_events
union all select 'knowledge_cases', count(*) from public.knowledge_cases
union all select 'parser_runs', count(*) from public.parser_runs
union all select 'user_feedback', count(*) from public.user_feedback
union all select 'solved_cases', count(*) from public.solved_cases
union all select 'video_library', count(*) from public.video_library
union all select 'media_files', count(*) from public.media_files
union all select 'messages', count(*) from public.messages
union all select 'conversations', count(*) from public.conversations
union all select 'diagnostic_requests', count(*) from public.diagnostic_requests
union all select 'dtc_errors', count(*) from public.dtc_errors
union all select 'vehicle_service_logs', count(*) from public.vehicle_service_logs
union all select 'users_kept', count(*) from public.users
union all select 'subscriptions_kept', count(*) from public.subscriptions
union all select 'payments_kept', count(*) from public.payments
union all select 'vehicles_kept', count(*) from public.vehicles
order by table_name;
