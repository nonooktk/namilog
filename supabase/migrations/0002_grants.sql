-- =============================================================================
-- Supabase ロールへのテーブル権限付与（RLS を安全境界とする Supabase 標準の考え方）
--
-- 背景（実スタック検証で判明・2026-07-12）:
--   `supabase db reset` はユーザーマイグレーション（0001_init.sql）を **postgres ロール**で
--   適用する。ところが本ローカルスタックの postgres の default privileges は anon/authenticated
--   に SELECT/INSERT/UPDATE を付与しない（TRUNCATE/REFERENCES/TRIGGER 相当のみ）。その結果、
--   API がユーザー文脈（role=authenticated）でアクセスすると RLS 判定以前に
--   「permission denied for table ...」になる。
--
--   Supabase では **テーブル権限は広めに付与し、行レベルの可視性は RLS が制御**する
--   （全ユーザーデータ表で RLS 有効・auth.uid()=user_id）。よって authenticated / service_role
--   にテーブル権限を明示付与する。anon には共有マスタの read も与えない（factor_catalog の
--   RLS が auth.role()='authenticated' を要求するため、anon には元々不要）。
--
--   これによりローカル/本番いずれの Supabase でも API が動作する（移行の自己完結性）。
-- =============================================================================

grant usage on schema public to authenticated, service_role;

-- 既存の全表（0001_init.sql で作成済み）への権限。行の可視性は各表の RLS が制御する。
-- authenticated: 本人操作（user_tx）で使う SELECT/INSERT/UPDATE（DELETE ポリシーは無いため付与しない）。
grant select, insert, update on all tables in schema public to authenticated;
-- service_role: バッチ等の特権用途（将来 service_role 接続に切替える場合の互換）。
grant select, insert, update, delete on all tables in schema public to service_role;

-- 今後追加される表にも同権限が自動付与されるよう既定権限を設定（postgres 作成分）。
alter default privileges in schema public
  grant select, insert, update on tables to authenticated;
alter default privileges in schema public
  grant select, insert, update, delete on tables to service_role;
