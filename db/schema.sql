drop table if exists knowledge_events cascade;
drop table if exists knowledge_cases cascade;
drop table if exists dtc_errors cascade;
drop table if exists service_history cascade;
drop table if exists media_files cascade;
drop table if exists diagnostic_requests cascade;
drop table if exists vehicles cascade;
drop table if exists vehicle_profiles cascade;
drop table if exists payments cascade;
drop table if exists subscriptions cascade;
drop table if exists user_sessions cascade;
drop table if exists users cascade;

create table users (
  id bigserial primary key,
  email text unique,
  google_id text unique,
  name text,
  language text not null default 'ru',
  country text,
  city text,
  subscription_plan text not null default 'free',
  subscription_status text not null default 'inactive',
  created_at timestamptz not null default now(),
  last_login timestamptz,
  requests_left integer not null default 10,
  conversation_history text,
  car_info text default '',
  auth_user_id text unique
);

create table vehicle_profiles (
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

create table user_sessions (
  id bigserial primary key,
  session_token text unique not null,
  user_id bigint not null references users(id) on delete cascade,
  source text not null default 'web',
  device text,
  last_seen_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create table subscriptions (
  id bigserial primary key,
  user_id bigint not null references users(id) on delete cascade,
  plan text not null default 'free',
  status text not null default 'inactive',
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

create table payments (
  id bigserial primary key,
  user_id bigint not null references users(id) on delete cascade,
  subscription_id bigint references subscriptions(id) on delete set null,
  provider text not null,
  provider_payment_id text unique,
  amount numeric(12, 2) not null,
  currency text not null default 'USD',
  status text not null default 'pending',
  paid_at timestamptz,
  created_at timestamptz not null default now()
);

create table vehicles (
  id bigserial primary key,
  user_id bigint not null references users(id) on delete cascade,
  vehicle_profile_id bigint references vehicle_profiles(id) on delete set null,
  brand text not null,
  model text not null,
  generation text,
  year integer,
  engine text,
  fuel text,
  transmission text,
  drive text,
  vin text,
  nickname text,
  mileage integer,
  photo_url text,
  displacement text,
  power text,
  torque text,
  engine_type text,
  cylinders text,
  emissions text,
  tank text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table diagnostic_requests (
  id bigserial primary key,
  user_id bigint not null references users(id) on delete cascade,
  vehicle_id bigint references vehicles(id) on delete set null,
  vehicle_profile_id bigint references vehicle_profiles(id) on delete set null,
  question text not null,
  answer text,
  language text not null default 'ru',
  request_type text not null default 'text',
  status text not null default 'new',
  source text not null default 'web',
  created_at timestamptz not null default now()
);

create table media_files (
  id bigserial primary key,
  user_id bigint not null references users(id) on delete cascade,
  vehicle_id bigint references vehicles(id) on delete set null,
  request_id bigint references diagnostic_requests(id) on delete set null,
  media_type text not null check (media_type in ('photo', 'video', 'audio', 'document')),
  file_url text not null,
  thumbnail_url text,
  duration integer,
  description text,
  created_at timestamptz not null default now()
);

create table service_history (
  id bigserial primary key,
  vehicle_id bigint not null references vehicles(id) on delete cascade,
  service_type text not null,
  description text,
  mileage integer,
  cost numeric(12, 2),
  service_date date,
  created_at timestamptz not null default now()
);

create table dtc_errors (
  id bigserial primary key,
  vehicle_id bigint not null references vehicles(id) on delete cascade,
  error_code text not null,
  description text,
  status text not null default 'active',
  first_seen timestamptz,
  last_seen timestamptz,
  created_at timestamptz not null default now()
);

create table knowledge_cases (
  id bigserial primary key,
  vehicle_profile_id bigint references vehicle_profiles(id) on delete set null,
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

create table knowledge_events (
  id bigserial primary key,
  vehicle_profile_id bigint references vehicle_profiles(id) on delete set null,
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

create index idx_users_email on users(email);
create index idx_users_auth_user_id on users(auth_user_id);
create index idx_users_google_id on users(google_id);
create index idx_user_sessions_user_last_seen on user_sessions(user_id, last_seen_at desc);
create index idx_subscriptions_user_status on subscriptions(user_id, status);
create index idx_payments_user_created on payments(user_id, created_at desc);
create index idx_vehicles_user_id on vehicles(user_id);
create index idx_diagnostic_requests_user_created on diagnostic_requests(user_id, created_at desc);
create index idx_diagnostic_requests_vehicle_created on diagnostic_requests(vehicle_id, created_at desc);
create index idx_media_files_request_id on media_files(request_id);
create index idx_service_history_vehicle_date on service_history(vehicle_id, service_date desc);
create index idx_dtc_errors_vehicle_code on dtc_errors(vehicle_id, error_code);
create index idx_knowledge_cases_profile_country on knowledge_cases(vehicle_profile_id, country);
create index idx_knowledge_events_profile_country on knowledge_events(vehicle_profile_id, country);
