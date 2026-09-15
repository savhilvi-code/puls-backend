-- PULS Backend V2 data contract reference.
-- Production Supabase is authoritative. Do not run this file against production
-- without an explicit migration review.

create extension if not exists pgcrypto;

create table if not exists public.users (
  id bigserial primary key,
  auth_user_id text unique,
  email text unique,
  name text,
  full_name text,
  language text not null default 'en',
  country text,
  city text,
  source text not null default 'web',
  created_at timestamptz not null default now(),
  last_login timestamptz,
  last_seen_at timestamptz
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
  quota_limit integer not null default 10,
  quota_used integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint subscriptions_quota_bounds check (quota_used >= 0 and quota_limit >= 0 and quota_used <= quota_limit)
);

create table if not exists public.payments (
  id bigserial primary key,
  user_id bigint references public.users(id) on delete set null,
  subscription_id bigint references public.subscriptions(id) on delete set null,
  provider text not null default 'system',
  provider_payment_id text unique,
  amount numeric(12, 2),
  currency text not null default 'USD',
  status text not null default 'pending',
  provider_metadata jsonb not null default '{}'::jsonb,
  paid_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists public.vehicles (
  id bigserial primary key,
  user_id bigint not null references public.users(id) on delete cascade,
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
  notes text,
  lifecycle_status text not null default 'ACTIVE',
  trashed_at timestamptz,
  restore_until timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.vehicle_specs (
  id bigserial primary key,
  vehicle_id bigint not null references public.vehicles(id) on delete cascade,
  specs jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.conversations (
  id bigserial primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  vehicle_id bigint references public.vehicles(id) on delete set null,
  problem_id bigint,
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
  problem_id bigint,
  role text not null,
  message_text text not null,
  language text not null default 'en',
  created_at timestamptz not null default now()
);

create table if not exists public.problems (
  id bigserial primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  vehicle_id bigint not null references public.vehicles(id) on delete cascade,
  title text not null,
  problem_class text not null default 'OTHER',
  component text,
  status text not null default 'OPEN',
  symptoms jsonb not null default '[]'::jsonb,
  conditions jsonb not null default '{}'::jsonb,
  confirmed_facts jsonb not null default '[]'::jsonb,
  hypotheses jsonb not null default '[]'::jsonb,
  checks_summary text,
  actions_summary text,
  current_conclusion text,
  next_step text,
  mileage integer,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  confirmation jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.conversations
  add constraint conversations_problem_id_fkey foreign key (problem_id) references public.problems(id) on delete set null;

alter table public.messages
  add constraint messages_problem_id_fkey foreign key (problem_id) references public.problems(id) on delete set null;

create table if not exists public.vehicle_events (
  id bigserial primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  vehicle_id bigint not null references public.vehicles(id) on delete cascade,
  problem_id bigint references public.problems(id) on delete set null,
  event_type text not null,
  title text,
  description text,
  event_data jsonb not null default '{}'::jsonb,
  mileage integer,
  source text not null default 'user',
  occurred_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create table if not exists public.vehicle_configurations (
  id bigserial primary key,
  vehicle_id bigint not null references public.vehicles(id) on delete cascade,
  configuration_type text not null,
  data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.fleet_events (
  id bigserial primary key,
  vehicle_signature jsonb not null default '{}'::jsonb,
  problem_class text,
  component text,
  symptom_summary text,
  confirmed_cause text,
  confirmed_solution text,
  confidence numeric(4, 3) not null default 0,
  source_problem_id bigint references public.problems(id) on delete set null,
  confirmation_data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.knowledge_items (
  id bigserial primary key,
  title text not null,
  summary text,
  content text,
  vehicle_make text,
  vehicle_model text,
  engine text,
  problem_class text,
  component text,
  confidence numeric(4, 3) not null default 0,
  provenance_type text not null default 'external',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.sources (
  id bigserial primary key,
  canonical_url text unique not null,
  title text,
  description text,
  source_type text not null default 'external',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.knowledge_sources (
  id bigserial primary key,
  knowledge_item_id bigint not null references public.knowledge_items(id) on delete cascade,
  source_id bigint not null references public.sources(id) on delete cascade,
  evidence_summary text,
  created_at timestamptz not null default now(),
  unique (knowledge_item_id, source_id)
);

create table if not exists public.problem_sources (
  id bigserial primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  problem_id bigint not null references public.problems(id) on delete cascade,
  source_id bigint not null references public.sources(id) on delete cascade,
  search_run_id bigint,
  evidence_summary text,
  relevance numeric(4, 3) not null default 0,
  created_at timestamptz not null default now()
);

create table if not exists public.search_episodes (
  id bigserial primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  vehicle_id bigint references public.vehicles(id) on delete set null,
  problem_id bigint not null references public.problems(id) on delete cascade,
  status text not null default 'RUNNING',
  reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.search_runs (
  id bigserial primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  search_episode_id bigint not null references public.search_episodes(id) on delete cascade,
  stage_number integer not null,
  run_type text not null,
  status text not null,
  query text,
  input_context jsonb not null default '{}'::jsonb,
  result_data jsonb not null default '{}'::jsonb,
  result_summary text,
  sources_found jsonb not null default '[]'::jsonb,
  relevant_sources jsonb not null default '[]'::jsonb,
  sufficient_evidence boolean not null default false,
  next_stage_reason text,
  provider text,
  model text,
  error_message text,
  created_at timestamptz not null default now(),
  unique (search_episode_id, stage_number)
);

alter table public.problem_sources
  add constraint problem_sources_search_run_id_fkey foreign key (search_run_id) references public.search_runs(id) on delete set null;

create index if not exists idx_subscriptions_user_status on public.subscriptions(user_id, status);
create index if not exists idx_payments_user_created on public.payments(user_id, created_at desc);
create index if not exists idx_vehicles_user_status on public.vehicles(user_id, lifecycle_status);
create index if not exists idx_conversations_user_updated on public.conversations(user_id, updated_at desc);
create index if not exists idx_messages_conversation_created on public.messages(conversation_id, created_at);
create index if not exists idx_problems_vehicle_status on public.problems(vehicle_id, status, updated_at desc);
create index if not exists idx_vehicle_events_vehicle_time on public.vehicle_events(vehicle_id, occurred_at desc);
create index if not exists idx_problem_sources_problem on public.problem_sources(problem_id);
create index if not exists idx_search_episodes_problem on public.search_episodes(problem_id, created_at desc);
create index if not exists idx_search_runs_episode_stage on public.search_runs(search_episode_id, stage_number);
