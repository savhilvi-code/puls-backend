create table if not exists public.reference_media (
  id bigserial primary key,
  media_type text not null check (media_type in ('image', 'video', 'webpage', 'document')),
  platform text,
  external_id text,
  canonical_url text not null,
  source_url text,
  thumbnail_url text,
  title text,
  description text,
  language text,
  vehicle_profile_id bigint references public.vehicle_profiles(id) on delete set null,
  brand text,
  model text,
  generation text,
  year_from integer,
  year_to integer,
  engine text,
  component text,
  subject text,
  reference_target text,
  relevance numeric,
  metadata jsonb,
  discovered_by_user_id bigint references public.users(id) on delete set null,
  first_seen_at timestamptz not null default now(),
  last_verified_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists idx_reference_media_canonical_url
  on public.reference_media(canonical_url);

create unique index if not exists idx_reference_media_platform_external_id
  on public.reference_media(platform, external_id)
  where platform is not null and external_id is not null;

create index if not exists idx_reference_media_subject_target
  on public.reference_media(subject, reference_target);

create index if not exists idx_reference_media_vehicle_context
  on public.reference_media(brand, model, generation, engine);

create index if not exists idx_reference_media_type_updated
  on public.reference_media(media_type, updated_at desc);

alter table public.reference_media enable row level security;

drop policy if exists reference_media_authenticated_read on public.reference_media;
create policy reference_media_authenticated_read
  on public.reference_media
  for select
  to authenticated
  using (true);
