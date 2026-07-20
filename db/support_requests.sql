create extension if not exists pgcrypto;

create table if not exists public.support_requests (
    id uuid primary key default gen_random_uuid(),
    user_id uuid null,
    email text not null,
    subject text not null,
    message text not null,
    attachment_url text null,
    status text not null default 'new',
    created_at timestamptz not null default now()
);

comment on table public.support_requests is 'PULS user support requests from the frontend support modal.';
comment on column public.support_requests.attachment_url is 'JSON array string with up to 3 public image URLs from the support-attachments storage bucket.';
