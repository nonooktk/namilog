-- ============================================================================
-- なみログ 本番バッチ セットアップ（Supabase pg_cron + pg_net）
-- 構成: A案（2026-07-12 統括承認）。ARCHITECTURE.md §7.5.1（cron 構成）/ §7.2（Vault 秘匿）。
--
-- 目的: FastAPI（Render）の内部エンドポイントを cron 式で定時起動する。
--   - 日次予測 (NL-API-16): POST /api/predictions/run … 毎朝 06:00 JST
--   - 週次ノート更新 (NL-API-17): POST /api/notes/refresh … 日曜 03:00 JST
--   併せて日次バッチが毎日 DB を触ることで、Supabase 無料枠の一時停止を回避する（§7.5）。
--
-- 認証: いずれも X-Batch-Token ヘッダに BATCH_INTERNAL_TOKEN を載せる。FastAPI 側は
--   fail-closed で照合する（deps/batch.py）。トークンは Supabase Vault に格納し、
--   この SQL や cron.schedule の本文に平文で書かない（セキュリティ規定1・4 / §7.2）。
--
-- 実行方法（Supabase ダッシュボード → SQL Editor、または supabase db execute）。
--   ※ 本ファイルはマイグレーション（supabase/migrations/）とは別の「本番セットアップ手順」。
--     プレースホルダ（<...>）を実値へ置換してから実行する。詳細は docs/DEPLOY.md ④。
-- ============================================================================

-- 0) 拡張の有効化（Supabase では管理 UI/SQL から有効化可能）。
create extension if not exists pg_cron;
create extension if not exists pg_net;
-- Vault はプロジェクト作成時に有効。未導入なら: create extension if not exists supabase_vault;

-- ----------------------------------------------------------------------------
-- 1) Vault に BATCH_INTERNAL_TOKEN を登録する（平文をジョブ定義に残さないため）。
--    Render の env（generateValue で生成）と「同一の値」を登録すること。
--    ※ 実値はここに書かず、下記コメントの手順どおり別途 1 回だけ実行する（このファイルはコミットするため）。
-- ----------------------------------------------------------------------------
-- 【手順・コミット禁止の実値で実行】既に存在する場合は update 側を使う。
--   select vault.create_secret('<RENDER が生成した BATCH_INTERNAL_TOKEN>', 'BATCH_INTERNAL_TOKEN');
-- 値を差し替える場合（id は vault.secrets から取得）:
--   select vault.update_secret(
--     (select id from vault.secrets where name = 'BATCH_INTERNAL_TOKEN'),
--     '<新しいトークン>', 'BATCH_INTERNAL_TOKEN');
-- 登録確認（値は表示しないこと）:
--   select name, created_at from vault.secrets where name = 'BATCH_INTERNAL_TOKEN';

-- ----------------------------------------------------------------------------
-- 2) 日次予測: 毎朝 06:00 JST（= 21:00 UTC 前日）。
--    Supabase の cron はサーバ TZ = UTC 基準。JST 06:00 = UTC 21:00。
--    <RENDER_SERVICE> は Render の本番ホスト名に置換（例: namilog-api.onrender.com）。
-- ----------------------------------------------------------------------------
select cron.schedule(
  'namilog-daily-predictions',
  '0 21 * * *',
  $$
  select net.http_post(
    url     := 'https://<RENDER_SERVICE>.onrender.com/api/predictions/run',
    headers := jsonb_build_object(
                 'Content-Type', 'application/json',
                 -- トークンは Vault から参照（平文で書かない・§7.2）
                 'X-Batch-Token', (select decrypted_secret
                                   from vault.decrypted_secrets
                                   where name = 'BATCH_INTERNAL_TOKEN')),
    body    := '{}'::jsonb
  );
  $$
);

-- ----------------------------------------------------------------------------
-- 3) 週次ノート更新: 日曜 03:00 JST（= 土曜 18:00 UTC）。
--    cron 曜日: 0/7=日, 6=土。JST 日曜 03:00 は UTC 土曜 18:00 のため '0 18 * * 6'。
-- ----------------------------------------------------------------------------
select cron.schedule(
  'namilog-weekly-notes',
  '0 18 * * 6',
  $$
  select net.http_post(
    url     := 'https://<RENDER_SERVICE>.onrender.com/api/notes/refresh',
    headers := jsonb_build_object(
                 'Content-Type', 'application/json',
                 'X-Batch-Token', (select decrypted_secret
                                   from vault.decrypted_secrets
                                   where name = 'BATCH_INTERNAL_TOKEN')),
    body    := '{}'::jsonb
  );
  $$
);

-- ----------------------------------------------------------------------------
-- 運用メモ
--  - 冪等性: predictions は upsert（§4.2）、週次ノートは同一 ISO 週スキップ（§7.5.1）で再実行に強い。
--    pg_net は非同期・タイムアウトありのため、Render Free のスリープ復帰（約1分）と重なって
--    応答を取りこぼしても、次回起動で追いつく（冪等設計）。
--  - target_date / base の既定は FastAPI 側で JST（app_today）に統一済み。プロセス TZ 非依存
--    なので body を空（'{}'）にしても正しい JST の日付で動く（M4前半 QA Major-1 是正）。
--  - 登録済みジョブの確認:   select jobid, jobname, schedule, active from cron.job;
--  - 実行履歴（失敗調査）:   select * from cron.job_run_details order by start_time desc limit 20;
--  - ジョブの解除（再登録前）: select cron.unschedule('namilog-daily-predictions');
--                              select cron.unschedule('namilog-weekly-notes');
-- ============================================================================
