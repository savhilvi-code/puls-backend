-- PULS web/Supabase integration layer.
-- Keeps existing tables/data and adds the missing web-first structures.

alter table public.users
  add column if not exists full_name text,
  add column if not exists source text not null default 'web',
  add column if not exists plan_type text not null default 'free',
  add column if not exists free_requests_limit integer not null default 10,
  add column if not exists free_requests_used integer not null default 0,
  add column if not exists paid_requests_limit integer not null default 100,
  add column if not exists paid_requests_used integer not null default 0,
  add column if not exists last_seen_at timestamptz;

alter table public.vehicles
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

alter table public.diagnostic_requests
  add column if not exists conversation_id bigint,
  add column if not exists symptoms text,
  add column if not exists raw_question text,
  add column if not exists parser_used boolean not null default false,
  add column if not exists deep_search_used boolean not null default false,
  add column if not exists request_cost_counted boolean not null default false,
  add column if not exists sources jsonb,
  add column if not exists videos jsonb,
  add column if not exists updated_at timestamptz not null default now();

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

create table if not exists public.video_library (
  id bigserial primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  vehicle_id bigint references public.vehicles(id) on delete set null,
  diagnostic_request_id bigint references public.diagnostic_requests(id) on delete set null,
  title text,
  url text not null,
  platform text,
  topic text,
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

create index if not exists idx_conversations_user_updated on public.conversations(user_id, updated_at desc);
create index if not exists idx_messages_conversation_created on public.messages(conversation_id, created_at);
create index if not exists idx_parser_runs_request on public.parser_runs(diagnostic_request_id);
create index if not exists idx_feedback_request on public.user_feedback(diagnostic_request_id);
create index if not exists idx_solved_cases_vehicle on public.solved_cases(vehicle_id, created_at desc);
create index if not exists idx_video_library_user on public.video_library(user_id, created_at desc);
