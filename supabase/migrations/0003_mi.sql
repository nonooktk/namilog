-- MI セッションは feedback_messages と完全に独立した追記型の会話記録。
create table public.mi_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  theme text,
  status text not null default 'active' check (status in ('active', 'closed', 'halted')),
  state jsonb not null default '{}'::jsonb,
  turn_count integer not null default 0,
  crisis_flag boolean not null default false,
  last_summary text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index idx_mi_sessions_user_updated on public.mi_sessions (user_id, updated_at desc);
create unique index uq_mi_sessions_active_user on public.mi_sessions (user_id) where status = 'active';
alter table public.mi_sessions enable row level security;
create policy "mi_sessions_select" on public.mi_sessions for select using (auth.uid() = user_id);
create policy "mi_sessions_insert" on public.mi_sessions for insert with check (auth.uid() = user_id);
create policy "mi_sessions_update" on public.mi_sessions for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create trigger trg_mi_sessions_updated_at before update on public.mi_sessions for each row execute function public.set_updated_at();

create table public.mi_messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.mi_sessions(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  is_verbatim boolean not null default false,
  turn_index integer not null,
  created_at timestamptz not null default now()
);
create index idx_mi_messages_session_turn on public.mi_messages (session_id, turn_index);
alter table public.mi_messages enable row level security;
create policy "mi_messages_select" on public.mi_messages for select using (auth.uid() = user_id);
create policy "mi_messages_insert" on public.mi_messages for insert with check (auth.uid() = user_id);

-- 0002 の default privileges が適用されるが、単独適用時にも自己完結するよう明示する。
grant select, insert, update on public.mi_sessions, public.mi_messages to authenticated;
grant select, insert, update, delete on public.mi_sessions, public.mi_messages to service_role;
