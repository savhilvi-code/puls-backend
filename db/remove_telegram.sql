-- Remove Telegram transport data from an existing Supabase project.
-- Run this once after deploying the code that no longer uses Telegram.

drop table if exists telegram_updates cascade;
drop table if exists telegram_messages cascade;

delete from public.diagnostic_requests
where source = 'telegram';

delete from public.user_sessions
where source = 'telegram';

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'users'
      and column_name = 'telegram_id'
  ) then
    delete from public.users
    where telegram_id is not null
      and email is null
      and google_id is null;

    alter table public.users drop column telegram_id;
  end if;
end $$;

drop index if exists idx_users_telegram_id;
