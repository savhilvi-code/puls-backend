-- PULS runtime alignment for the current backend service-layer.
-- Safe to run multiple times in Supabase SQL Editor.

alter table if exists public.users
  add column if not exists full_name text,
  add column if not exists source text not null default 'web',
  add column if not exists last_seen_at timestamptz;

create table if not exists public.subscriptions (
  id bigserial primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  plan text not null default 'free',
  status text not null default 'active',
  provider text,
  provider_customer_id text,
  provider_subscription_id text,
  current_period_start timestamptz,
  current_period_end timestamptz,
  cancel_at_period_end boolean not null default false,
  requests_limit integer,
  requests_used integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.payments (
  id bigserial primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  subscription_id bigint references public.subscriptions(id) on delete set null,
  provider text not null default 'system',
  provider_payment_id text unique,
  amount numeric(12, 2),
  currency text not null default 'USD',
  status text not null default 'pending',
  paid_at timestamptz,
  created_at timestamptz not null default now()
);

alter table if exists public.vehicles
  add column if not exists country text,
  add column if not exists city text,
  add column if not exists fuel_type text,
  add column if not exists displacement text,
  add column if not exists power text,
  add column if not exists torque text,
  add column if not exists engine_type text,
  add column if not exists cylinders text,
  add column if not exists emissions text,
  add column if not exists tank text,
  add column if not exists notes text;

alter table if exists public.diagnostic_requests
  add column if not exists conversation_id bigint,
  add column if not exists raw_question text,
  add column if not exists symptoms text,
  add column if not exists parser_used boolean not null default false,
  add column if not exists deep_search_used boolean not null default false,
  add column if not exists request_cost_counted boolean not null default false,
  add column if not exists sources jsonb,
  add column if not exists videos jsonb,
  add column if not exists updated_at timestamptz not null default now(),
  add column if not exists brand text,
  add column if not exists model text,
  add column if not exists year integer,
  add column if not exists engine text;

create table if not exists public.conversations (
  id bigserial primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  vehicle_id bigint references public.vehicles(id) on delete set null,
  channel text not null default 'site',
  status text not null default 'active',
  title text,
  last_message_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.messages (
  id bigserial primary key,
  conversation_id bigint not null references public.conversations(id) on delete cascade,
  user_id bigint not null references public.users(id) on delete cascade,
  vehicle_id bigint references public.vehicles(id) on delete set null,
  role text not null,
  message_text text not null,
  language text not null default 'ru',
  created_at timestamptz not null default now()
);

create table if not exists public.parser_runs (
  id bigserial primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  vehicle_id bigint references public.vehicles(id) on delete set null,
  conversation_id bigint references public.conversations(id) on delete set null,
  diagnostic_request_id bigint references public.diagnostic_requests(id) on delete set null,
  run_type text not null,
  query_original text,
  query_translated text,
  languages_used jsonb,
  forums_used jsonb,
  sources_found jsonb,
  videos_found jsonb,
  tokens_used integer,
  created_at timestamptz not null default now()
);

create table if not exists public.user_feedback (
  id bigserial primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  vehicle_id bigint references public.vehicles(id) on delete set null,
  conversation_id bigint references public.conversations(id) on delete set null,
  diagnostic_request_id bigint references public.diagnostic_requests(id) on delete set null,
  feedback_type text not null,
  feedback_text text,
  created_at timestamptz not null default now()
);

create table if not exists public.solved_cases (
  id bigserial primary key,
  user_id bigint references public.users(id) on delete set null,
  vehicle_id bigint references public.vehicles(id) on delete set null,
  diagnostic_request_id bigint references public.diagnostic_requests(id) on delete set null,
  brand text,
  model text,
  year integer,
  engine text,
  symptoms text,
  confirmed_problem text,
  confirmed_solution text,
  sources jsonb,
  videos jsonb,
  confidence numeric(4, 3) not null default 0.5,
  created_at timestamptz not null default now()
);

create table if not exists public.vehicle_service_logs (
  id bigserial primary key,
  user_id bigint references public.users(id) on delete cascade,
  vehicle_id bigint not null references public.vehicles(id) on delete cascade,
  service_type text,
  service_name text,
  description text,
  mileage integer,
  service_date date,
  parts_used text,
  notes text,
  created_at timestamptz not null default now()
);

create table if not exists public.media_files (
  id bigserial primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  vehicle_id bigint references public.vehicles(id) on delete set null,
  request_id bigint references public.diagnostic_requests(id) on delete set null,
  media_type text not null check (media_type in ('photo', 'video', 'audio', 'document')),
  file_url text not null,
  thumbnail_url text,
  duration integer,
  description text,
  created_at timestamptz not null default now()
);

create index if not exists idx_conversations_user_updated on public.conversations(user_id, updated_at desc);
create index if not exists idx_messages_conversation_created on public.messages(conversation_id, created_at);
create index if not exists idx_parser_runs_request on public.parser_runs(diagnostic_request_id);
create index if not exists idx_feedback_request on public.user_feedback(diagnostic_request_id);
create index if not exists idx_solved_cases_vehicle on public.solved_cases(vehicle_id, created_at desc);
create index if not exists idx_media_files_request on public.media_files(request_id);
create index if not exists idx_subscriptions_user_status on public.subscriptions(user_id, status);

-- Optional cleanup for already-corrupted solved cases.
-- Review the SELECT first, then run the DELETE if the rows are действительно ошибочные.

select id, vehicle_id, brand, model, year, engine, symptoms
from public.solved_cases
where (lower(coalesce(brand, '')) like 'nissan%' and lower(coalesce(symptoms, '')) like '%toyota%')
   or (lower(coalesce(brand, '')) like 'toyota%' and lower(coalesce(symptoms, '')) like '%nissan%');

-- delete from public.solved_cases
-- where (lower(coalesce(brand, '')) like 'nissan%' and lower(coalesce(symptoms, '')) like '%toyota%')
--    or (lower(coalesce(brand, '')) like 'toyota%' and lower(coalesce(symptoms, '')) like '%nissan%');
