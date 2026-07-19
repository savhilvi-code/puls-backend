-- Canonical PULS production schema.
-- This file is the single source of truth for the current backend persistence layer.
-- Use this file for fresh environments and for auditing live Supabase against backend expectations.
-- Legacy files kept for reference:
--   - schema.sql: old bootstrap schema
--   - puls_integration.sql: transitional web integration changes
--   - puls_supabase_alignment.sql: transitional runtime alignment changes

create extension if not exists pgcrypto;

create table if not exists public.users (
  id bigserial primary key,
  email text unique,
  google_id text unique,
  name text,
  full_name text,
  language text not null default 'ru',
  country text,
  city text,
  source text not null default 'web',
  subscription_plan text not null default 'free',
  subscription_status text not null default 'inactive',
  plan_type text not null default 'free',
  free_requests_limit integer not null default 10,
  free_requests_used integer not null default 0,
  paid_requests_limit integer not null default 100,
  paid_requests_used integer not null default 0,
  created_at timestamptz not null default now(),
  last_login timestamptz,
  last_seen_at timestamptz,
  requests_left integer not null default 10,
  conversation_history text,
  car_info text default '',
  auth_user_id text unique
);

create table if not exists public.vehicle_profiles (
  id bigserial primary key,
  brand text not null,
  model text not null,
  generation text,
  year_from integer,
  year_to integer,
  engine text,
  fuel text,
  drive text,
  transmission text,
  market text,
  created_at timestamptz not null default now()
);

create table if not exists public.user_sessions (
  id bigserial primary key,
  session_token text unique not null,
  user_id bigint not null references public.users(id) on delete cascade,
  source text not null default 'web',
  device text,
  last_seen_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

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

create table if not exists public.vehicles (
  id bigserial primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  vehicle_profile_id bigint references public.vehicle_profiles(id) on delete set null,
  brand text not null,
  model text not null,
  generation text,
  year integer,
  engine text,
  fuel text,
  fuel_type text,
  transmission text,
  drive text,
  vin text,
  nickname text,
  mileage integer,
  photo_url text,
  country text,
  city text,
  displacement text,
  power text,
  torque text,
  engine_type text,
  cylinders text,
  emissions text,
  tank text,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

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

create table if not exists public.diagnostic_requests (
  id bigserial primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  vehicle_id bigint references public.vehicles(id) on delete set null,
  vehicle_profile_id bigint references public.vehicle_profiles(id) on delete set null,
  conversation_id bigint references public.conversations(id) on delete set null,
  question text not null,
  raw_question text,
  symptoms text,
  answer text,
  language text not null default 'ru',
  request_type text not null default 'text',
  status text not null default 'new',
  source text not null default 'web',
  parser_used boolean not null default false,
  deep_search_used boolean not null default false,
  request_cost_counted boolean not null default false,
  sources jsonb,
  videos jsonb,
  brand text,
  model text,
  year integer,
  engine text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
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

create table if not exists public.knowledge_cases (
  id bigserial primary key,
  vehicle_profile_id bigint references public.vehicle_profiles(id) on delete set null,
  country text,
  symptom_title text not null,
  symptom_description text,
  confirmed_cause text,
  recommended_action text,
  success_count integer not null default 0,
  confidence numeric(4, 3) not null default 0,
  source_type text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  full_answer text,
  raw_payload jsonb,
  forum_links jsonb
);

create table if not exists public.knowledge_events (
  id bigserial primary key,
  vehicle_profile_id bigint references public.vehicle_profiles(id) on delete set null,
  country text,
  symptom text not null,
  cause text,
  solution text,
  result text,
  mileage integer,
  temperature numeric(5, 2),
  source text not null default 'user',
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

create table if not exists public.dtc_errors (
  id bigserial primary key,
  vehicle_id bigint not null references public.vehicles(id) on delete cascade,
  error_code text not null,
  description text,
  status text not null default 'active',
  first_seen timestamptz,
  last_seen timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists idx_users_email on public.users(email);
create index if not exists idx_users_auth_user_id on public.users(auth_user_id);
create index if not exists idx_users_google_id on public.users(google_id);
create index if not exists idx_user_sessions_user_last_seen on public.user_sessions(user_id, last_seen_at desc);
create index if not exists idx_subscriptions_user_status on public.subscriptions(user_id, status);
create index if not exists idx_payments_user_created on public.payments(user_id, created_at desc);
create index if not exists idx_vehicles_user_id on public.vehicles(user_id);
create index if not exists idx_conversations_user_updated on public.conversations(user_id, updated_at desc);
create index if not exists idx_messages_conversation_created on public.messages(conversation_id, created_at);
create index if not exists idx_diagnostic_requests_user_created on public.diagnostic_requests(user_id, created_at desc);
create index if not exists idx_diagnostic_requests_vehicle_created on public.diagnostic_requests(vehicle_id, created_at desc);
create index if not exists idx_parser_runs_request on public.parser_runs(diagnostic_request_id);
create index if not exists idx_feedback_request on public.user_feedback(diagnostic_request_id);
create index if not exists idx_solved_cases_vehicle on public.solved_cases(vehicle_id, created_at desc);
create index if not exists idx_video_library_user on public.video_library(user_id, created_at desc);
create index if not exists idx_media_files_request on public.media_files(request_id);
create index if not exists idx_dtc_errors_vehicle_code on public.dtc_errors(vehicle_id, error_code);
create index if not exists idx_vehicle_service_logs_vehicle_date on public.vehicle_service_logs(vehicle_id, service_date desc);
create index if not exists idx_knowledge_cases_profile_country on public.knowledge_cases(vehicle_profile_id, country);
create index if not exists idx_knowledge_events_profile_country on public.knowledge_events(vehicle_profile_id, country);
