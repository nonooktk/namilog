-- =============================================================================
-- 【テスト専用シム】Supabase 相当の auth スキーマ／ロールをローカル Postgres 上に再現する。
--
-- ⚠ これはアプリ本体の一部ではない。Supabase CLI（`supabase start`）が使えない環境で、
--   マイグレーション（0001_init.sql）・RLS ポリシー・API ロジックを Docker の Postgres
--   （pgvector 入り）だけで検証するための最小ハーネス。実際の開発／本番は Supabase の
--   本物の auth（GoTrue）とロールを使う。
--
-- 再現するもの:
--   - ロール anon / authenticated / service_role
--   - auth スキーマと auth.users（トリガー連携に必要な最小カラム）
--   - auth.uid() / auth.role()（request.jwt.claims から sub/role を取り出す）
--   - authenticated への既定権限（Supabase では authenticated にテーブル権限が付与され、
--     行の可視性は RLS が制御する）
-- =============================================================================

-- ロール（Supabase 相当）
do $$
begin
  if not exists (select from pg_roles where rolname = 'anon') then
    create role anon nologin noinherit;
  end if;
  if not exists (select from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin noinherit;
  end if;
  if not exists (select from pg_roles where rolname = 'service_role') then
    create role service_role nologin noinherit bypassrls;
  end if;
end $$;

-- auth スキーマと最小 users テーブル（FK 先＋トリガー連携）
create schema if not exists auth;
create table if not exists auth.users (
  id uuid primary key default gen_random_uuid(),
  email text unique,
  raw_user_meta_data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- auth.uid() / auth.role()（request.jwt.claims から取り出す。Supabase の実装に準拠）
create or replace function auth.uid() returns uuid
language sql stable as $$
  select (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid
$$;

create or replace function auth.role() returns text
language sql stable as $$
  select nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'role'
$$;

-- 認証ロールがスキーマ／関数を使えるように
grant usage on schema public, auth to anon, authenticated, service_role;
grant execute on function auth.uid(), auth.role() to anon, authenticated, service_role;

-- postgres がこの後 public に作るテーブルへ、authenticated/service_role に権限を既定付与する。
-- （行の可視性は各テーブルの RLS が制御する。Supabase の権限モデルを模倣。）
alter default privileges in schema public
  grant select, insert, update, delete on tables to authenticated, service_role;
alter default privileges in schema public
  grant usage, select on sequences to authenticated, service_role;
