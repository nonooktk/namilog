-- =============================================================================
-- 期間ダイジェスト digests（ARCHITECTURE.md §2.12 / NL-API-19 / §4.6）
--   - 指定期間（period_from〜period_to）の体調を GPT で要約した「期間ダイジェスト」を保持。
--   - 同一ユーザー・同一期間は unique 制約で1件に制約し、再リクエストは保存済み content を
--     再利用する（再生成なし＝LLM コスト対策 §4.6）。強制再生成は API の force で upsert。
--   - 全ユーザーデータ表と同方針で RLS を有効化し「本人の行のみ read/write」を強制（P-2）。
-- =============================================================================
create table public.digests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  period_from date not null,
  period_to date not null,
  -- {summary, good_days:[{date,note,coping}], bad_days:[{date,note,coping}]}（§4.6 の json_schema と一致）
  content jsonb not null,
  model text not null default 'gpt-4o-mini',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  -- 同一ユーザー・同一期間のダイジェストは1件（取得時はこのキーで既存検索→再利用）。
  -- この unique 制約が (user_id, period_from, period_to) の btree インデックスを兼ねるため、
  -- 取得クエリ（同キーの完全一致）はこれで賄える。冗長な同列インデックスは作らない（レビュー#6）。
  unique (user_id, period_from, period_to)
);

alter table public.digests enable row level security;
create policy "digests_select" on public.digests for select using (auth.uid() = user_id);
create policy "digests_insert" on public.digests for insert with check (auth.uid() = user_id);
create policy "digests_update" on public.digests for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- 行更新時に updated_at を自動更新（既存表と同じ set_updated_at() を再利用。0001 で定義済み）。
create trigger trg_digests_updated_at
  before update on public.digests
  for each row execute function public.set_updated_at();

-- 0002 の alter default privileges で authenticated / service_role に権限が自動付与されるが、
-- 本マイグレーション単独適用時にも自己完結するよう明示する（0003 と同方針）。
grant select, insert, update on public.digests to authenticated;
grant select, insert, update, delete on public.digests to service_role;
