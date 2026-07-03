-- Clean all current test users and their related PULS data.
-- Run manually in Supabase SQL Editor for the test project only.
--
-- This script intentionally leaves shared reference/knowledge tables intact:
-- vehicle_profiles, knowledge_cases, knowledge_events, dtc_errors.

begin;

-- Delete child tables first to avoid orphan data and FK conflicts.
delete from public.parser_runs
where user_id in (select id from public.users)
   or diagnostic_request_id in (select id from public.diagnostic_requests);

delete from public.user_feedback
where user_id in (select id from public.users)
   or diagnostic_request_id in (select id from public.diagnostic_requests)
   or conversation_id in (select id from public.conversations);

delete from public.solved_cases
where user_id in (select id from public.users)
   or diagnostic_request_id in (select id from public.diagnostic_requests);

delete from public.video_library
where user_id in (select id from public.users)
   or diagnostic_request_id in (select id from public.diagnostic_requests);

delete from public.messages
where user_id in (select id from public.users)
   or conversation_id in (select id from public.conversations);

delete from public.conversations
where user_id in (select id from public.users);

delete from public.vehicle_service_logs
where user_id in (select id from public.users)
   or vehicle_id in (select id from public.vehicles);

delete from public.media_files
where user_id in (select id from public.users)
   or request_id in (select id from public.diagnostic_requests);

delete from public.service_history
where vehicle_id in (select id from public.vehicles);

delete from public.diagnostic_requests
where user_id in (select id from public.users);

delete from public.payments
where user_id in (select id from public.users)
   or subscription_id in (select id from public.subscriptions);

delete from public.subscriptions
where user_id in (select id from public.users);

delete from public.user_sessions
where user_id in (select id from public.users);

delete from public.vehicles
where user_id in (select id from public.users);

-- Final user cleanup. The requested patterns are covered because the goal is
-- a fully empty public.users table.
delete from public.users
where true;

-- Also try to remove matching Supabase Auth users when SQL Editor has access.
-- Public cleanup above remains the source of truth for the PULS database.
do $$
begin
  delete from auth.users
  where email in ('sav.kvazar@gmail.com', 'sav.kvazar@mail.com', 'test@example.com')
     or email ilike 'stateful-%'
     or email ilike 'puls-flow-%'
     or email ilike 'debug-%'
     or email ilike '%@example.com';
exception
  when insufficient_privilege then
    raise notice 'Skipped auth.users cleanup: insufficient privilege.';
  when undefined_table then
    raise notice 'Skipped auth.users cleanup: auth.users table is not available.';
end $$;

commit;

-- Verification: users must be empty.
select 'users' as table_name, count(*) as rows_count from public.users;

-- Verification: all user-owned tables should be empty.
select 'messages' as table_name, count(*) as rows_count from public.messages
union all select 'conversations', count(*) from public.conversations
union all select 'diagnostic_requests', count(*) from public.diagnostic_requests
union all select 'parser_runs', count(*) from public.parser_runs
union all select 'user_feedback', count(*) from public.user_feedback
union all select 'solved_cases', count(*) from public.solved_cases
union all select 'video_library', count(*) from public.video_library
union all select 'vehicle_service_logs', count(*) from public.vehicle_service_logs
union all select 'vehicles', count(*) from public.vehicles
union all select 'user_sessions', count(*) from public.user_sessions
union all select 'subscriptions', count(*) from public.subscriptions
union all select 'payments', count(*) from public.payments
union all select 'media_files', count(*) from public.media_files
union all select 'service_history', count(*) from public.service_history
order by table_name;

-- Verification: orphan checks for user/vehicle/conversation/request links.
select 'messages.user_id' as check_name, count(*) as orphan_count
from public.messages m
left join public.users u on u.id = m.user_id
where m.user_id is not null and u.id is null
union all
select 'messages.conversation_id', count(*)
from public.messages m
left join public.conversations c on c.id = m.conversation_id
where m.conversation_id is not null and c.id is null
union all
select 'conversations.user_id', count(*)
from public.conversations c
left join public.users u on u.id = c.user_id
where c.user_id is not null and u.id is null
union all
select 'diagnostic_requests.user_id', count(*)
from public.diagnostic_requests d
left join public.users u on u.id = d.user_id
where d.user_id is not null and u.id is null
union all
select 'diagnostic_requests.vehicle_id', count(*)
from public.diagnostic_requests d
left join public.vehicles v on v.id = d.vehicle_id
where d.vehicle_id is not null and v.id is null
union all
select 'parser_runs.diagnostic_request_id', count(*)
from public.parser_runs p
left join public.diagnostic_requests d on d.id = p.diagnostic_request_id
where p.diagnostic_request_id is not null and d.id is null
union all
select 'user_feedback.diagnostic_request_id', count(*)
from public.user_feedback f
left join public.diagnostic_requests d on d.id = f.diagnostic_request_id
where f.diagnostic_request_id is not null and d.id is null
union all
select 'solved_cases.diagnostic_request_id', count(*)
from public.solved_cases s
left join public.diagnostic_requests d on d.id = s.diagnostic_request_id
where s.diagnostic_request_id is not null and d.id is null
union all
select 'video_library.diagnostic_request_id', count(*)
from public.video_library v
left join public.diagnostic_requests d on d.id = v.diagnostic_request_id
where v.diagnostic_request_id is not null and d.id is null
union all
select 'vehicle_service_logs.vehicle_id', count(*)
from public.vehicle_service_logs l
left join public.vehicles v on v.id = l.vehicle_id
where l.vehicle_id is not null and v.id is null
order by check_name;
