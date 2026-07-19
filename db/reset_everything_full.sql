-- Full reset of PULS public data.
--
-- Recommended only when:
-- - you want a completely fresh project state
-- - you are fine losing users, vehicles, subscriptions, payments, history,
--   solved cases, knowledge base, and runtime artifacts
--
-- Run manually in Supabase SQL Editor with owner/service privileges.

begin;

delete from public.knowledge_events;
delete from public.knowledge_cases;
delete from public.parser_runs;
delete from public.user_feedback;
delete from public.solved_cases;
delete from public.video_library;
delete from public.media_files;
delete from public.messages;
delete from public.conversations;
delete from public.vehicle_service_logs;
delete from public.dtc_errors;
delete from public.diagnostic_requests;
delete from public.payments;
delete from public.subscriptions;
delete from public.user_sessions;
delete from public.vehicles;
delete from public.users;

do $$
begin
  delete from auth.users;
exception
  when insufficient_privilege then
    raise notice 'Skipped auth.users cleanup: insufficient privilege.';
  when undefined_table then
    raise notice 'Skipped auth.users cleanup: auth.users table is not available.';
end $$;

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
union all select 'payments', count(*) from public.payments
union all select 'subscriptions', count(*) from public.subscriptions
union all select 'user_sessions', count(*) from public.user_sessions
union all select 'vehicles', count(*) from public.vehicles
union all select 'users', count(*) from public.users
order by table_name;
