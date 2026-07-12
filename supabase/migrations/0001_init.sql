-- =============================================================================
-- なみログ 初期スキーマ（ARCHITECTURE.md §2 の DDL を版管理）
--   - 全ユーザーデータ表で RLS を有効化し「本人の行のみ read/write」を強制（P-2）
--   - 外部指標は不変の論理キー factor_key で JSONB に全件蓄積（P-3）
--   - profiles は auth.users への after insert トリガーで自動生成（§2.2 補足）
-- =============================================================================

-- 0) 拡張（Supabase では概ね導入済みだが明示する。§2.1）
create extension if not exists pgcrypto;   -- gen_random_uuid()
create extension if not exists vector;     -- pgvector（類似日検索）

-- -----------------------------------------------------------------------------
-- 共通: updated_at 自動更新トリガー関数（保守性のため。行更新時に now() を書き込む）
-- -----------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- =============================================================================
-- 2.2 profiles（プロフィール：Supabase Auth 連携）
-- =============================================================================
create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  -- Open-Meteo 用の粗い緯度経度（プライバシー配慮で小数2桁＝約1km粒度に丸めて保存）
  latitude  numeric(6,2),
  longitude numeric(6,2),
  timezone text not null default 'Asia/Tokyo',
  medical_disclaimer_agreed_at timestamptz,   -- 医療免責への同意時刻（オンボーディング）
  onboarded_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.profiles enable row level security;
create policy "profiles_select" on public.profiles for select using (auth.uid() = id);
create policy "profiles_insert" on public.profiles for insert with check (auth.uid() = id);
create policy "profiles_update" on public.profiles for update using (auth.uid() = id) with check (auth.uid() = id);

create trigger trg_profiles_updated_at
  before update on public.profiles
  for each row execute function public.set_updated_at();

-- auth.users 作成時に public.profiles を自動生成（§2.2 補足。M2 で実装）
-- security definer で RLS を跨いで insert する。search_path は固定して安全に。
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name'))
  on conflict (id) do nothing;
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- =============================================================================
-- 2.3 daily_records（実測スコア・コメント・日付）
-- =============================================================================
create table public.daily_records (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  record_date date not null,
  actual_score smallint not null check (actual_score between 1 and 10),
  comment text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, record_date)              -- 1日1レコード
);
create index idx_daily_records_user_date on public.daily_records (user_id, record_date desc);

alter table public.daily_records enable row level security;
create policy "dr_select" on public.daily_records for select using (auth.uid() = user_id);
create policy "dr_insert" on public.daily_records for insert with check (auth.uid() = user_id);
create policy "dr_update" on public.daily_records for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

create trigger trg_daily_records_updated_at
  before update on public.daily_records
  for each row execute function public.set_updated_at();

-- =============================================================================
-- 2.4 predictions（予測スコア・対策・根拠・対象日・実測との誤差）
-- =============================================================================
create table public.predictions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  target_date date not null,                 -- 予測対象日（＝「明日」）
  predicted_score smallint not null check (predicted_score between 1 and 10),
  advice text not null,                      -- 一言対策
  rationale text not null,                   -- 根拠（本人向けの説明）
  factor_snapshot jsonb,                     -- 予測時に使った3指標の値スナップショット
  note_version int,                          -- 使用した予測ノートのバージョン
  similar_dates date[],                      -- few-shot に使った類似日（トレース用）
  crisis_flag boolean not null default false,-- 予測パイプラインが検知した危機兆候
  model text not null default 'gpt-4o-mini',
  -- 実測突合（翌日確定時に明示ステップで埋める。P-4）
  actual_score smallint,                     -- 冗長保持だが誤差の即時算出のため
  error smallint,                            -- 符号付き誤差 = actual - predicted
  abs_error smallint,                        -- 絶対誤差
  scored_at timestamptz,                     -- 突合した時刻
  created_at timestamptz not null default now(),
  unique (user_id, target_date)              -- 対象日ごとに最新1件（再実行は upsert）
);
create index idx_predictions_user_date on public.predictions (user_id, target_date desc);

alter table public.predictions enable row level security;
create policy "pred_select" on public.predictions for select using (auth.uid() = user_id);
create policy "pred_insert" on public.predictions for insert with check (auth.uid() = user_id);
create policy "pred_update" on public.predictions for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- =============================================================================
-- 2.5 factor_catalog（12 指標マスタ：補助表・全ユーザー共通の read-only 共有）
-- =============================================================================
create table public.factor_catalog (
  factor_key text primary key,               -- 安定した論理キー（P-3）例: 'barometric_pressure'
  label text not null,                       -- 例: '気圧（低下傾向）'
  input_type text not null check (input_type in ('open_meteo','derived','manual')),
  unit text,                                 -- 例: 'hPa','hours','℃'
  description text,
  sort_order int not null default 0
);

alter table public.factor_catalog enable row level security;
create policy "catalog_read" on public.factor_catalog
  for select using (auth.role() = 'authenticated');  -- 認証済みは全員閲覧可・書込不可

-- =============================================================================
-- 2.6 external_factors（選択中の3指標と履歴：行は消さず期間で管理。P-3）
-- =============================================================================
create table public.external_factors (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  factor_key text not null references public.factor_catalog(factor_key),
  is_active boolean not null default true,
  activated_at   timestamptz not null default now(),
  deactivated_at timestamptz,                -- 非選択化しても行は消さず期間で管理
  created_at timestamptz not null default now()
);
create index idx_external_factors_active on public.external_factors (user_id) where is_active;
-- アクティブは同一 factor_key で1行に限定（重複アクティブ防止）
create unique index uq_external_factors_active_key
  on public.external_factors (user_id, factor_key) where is_active;
-- 「アクティブは最大3つ」はアプリ層（§5.3）で強制。DB では上記で重複だけ封じる。

alter table public.external_factors enable row level security;
create policy "ef_select" on public.external_factors for select using (auth.uid() = user_id);
create policy "ef_insert" on public.external_factors for insert with check (auth.uid() = user_id);
create policy "ef_update" on public.external_factors for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- =============================================================================
-- 2.7 factor_values（日次の外部指標値：JSONB。全指標を蓄積し利用は選択的。P-3）
-- =============================================================================
create table public.factor_values (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  value_date date not null,
  -- 例: {"barometric_pressure":{"v":1004.2,"unit":"hPa","src":"open_meteo"},
  --      "sleep":{"v":6.5,"unit":"hours","src":"manual"}}
  values jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  unique (user_id, value_date)
);
create index idx_factor_values_gin on public.factor_values using gin (values);

alter table public.factor_values enable row level security;
create policy "fv_select" on public.factor_values for select using (auth.uid() = user_id);
create policy "fv_insert" on public.factor_values for insert with check (auth.uid() = user_id);
create policy "fv_update" on public.factor_values for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

create trigger trg_factor_values_updated_at
  before update on public.factor_values
  for each row execute function public.set_updated_at();

-- =============================================================================
-- 2.8 prediction_notes（予測ノート：版管理・追記型）
-- =============================================================================
create table public.prediction_notes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  version int not null,
  content text not null,
  is_current boolean not null default true,
  source text not null default 'weekly_batch' check (source in ('weekly_batch','manual','onboarding')),
  created_at timestamptz not null default now(),
  unique (user_id, version)
);
-- ユーザーごとに現行版は1つだけ
create unique index uq_notes_current on public.prediction_notes (user_id) where is_current;

alter table public.prediction_notes enable row level security;
create policy "pn_select" on public.prediction_notes for select using (auth.uid() = user_id);
create policy "pn_insert" on public.prediction_notes for insert with check (auth.uid() = user_id);
create policy "pn_update" on public.prediction_notes for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- =============================================================================
-- 2.9 feedback_messages（FB チャット）
-- =============================================================================
create table public.feedback_messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  prediction_id uuid references public.predictions(id) on delete set null,
  role text not null check (role in ('user','assistant')),
  content text not null,
  created_at timestamptz not null default now()
);
create index idx_feedback_user_time on public.feedback_messages (user_id, created_at);

alter table public.feedback_messages enable row level security;
create policy "fb_select" on public.feedback_messages for select using (auth.uid() = user_id);
create policy "fb_insert" on public.feedback_messages for insert with check (auth.uid() = user_id);

-- =============================================================================
-- 2.10 comment_embeddings（pgvector：類似日検索。text-embedding-3-small = 1536次元）
-- =============================================================================
create table public.comment_embeddings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  daily_record_id uuid not null references public.daily_records(id) on delete cascade,
  record_date date not null,
  embedding vector(1536) not null,
  model text not null default 'text-embedding-3-small',
  created_at timestamptz not null default now(),
  unique (daily_record_id)
);
-- コサイン距離の近似最近傍（HNSW）
create index idx_comment_embeddings_hnsw
  on public.comment_embeddings using hnsw (embedding vector_cosine_ops);

alter table public.comment_embeddings enable row level security;
create policy "ce_select" on public.comment_embeddings for select using (auth.uid() = user_id);
create policy "ce_insert" on public.comment_embeddings for insert with check (auth.uid() = user_id);
