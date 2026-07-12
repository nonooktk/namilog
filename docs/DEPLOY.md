# なみログ 本番デプロイ手順書

構成: **A案（2026-07-12 統括承認）** — フロント=**Vercel** / バックエンド=**Render Free** /
DB・Auth=**Supabase クラウド** / バッチ=**Supabase pg_cron + pg_net**。
根拠: `ARCHITECTURE.md` §1.2 / §7.2 / §7.5.1、`設計/ホスティング比較.md`（A案）。

> [!important] このドキュメントの前提
> - 実際のクラウド操作（Supabase プロジェクト作成・Vercel/Render のダッシュボード設定・Google
>   OAuth クレデンシャル発行）は **統括（mitsuru さん）が実施** します。本書はその順序と、
>   リポジトリ内の設定物（`render.yaml` / `supabase/cron.sql` / マイグレーション）の使い方をまとめます。
> - **秘匿値は絶対にコミット・Slack 投稿しない**（[[セキュリティ規定]]）。`.env` はローカルのみ。
> - デプロイは **ローカル動作確認と統括の明示的承認後** に行う（[[リリース規定]]）。

デプロイ順序（依存関係）: **① Supabase → ② Render → ③ Vercel → ④ cron/Vault → ⑤ スモーク**。
（Render は Supabase の URL/鍵が要る。Vercel は Render の API URL が要る。cron は Render のホスト名が要る。）

---

## 必要な環境変数（一覧・名前と説明のみ）

秘匿値は各サービスのダッシュボードで設定する（値は本書に書かない）。

### Render（バックエンド FastAPI）

| 変数名 | 設定方法 | 説明 |
| --- | --- | --- |
| `APP_ENV` | Blueprint 固定 = `production` | production では JWT 構成の安全性を起動時に強制（`config.py`）。 |
| `PYTHON_VERSION` | Blueprint 固定 = `3.11.9` | ビルド時 Python を固定。 |
| `SUPABASE_URL` | ダッシュボード（sync:false） | `https://<PROJECT_REF>.supabase.co` |
| `SUPABASE_ANON_KEY` | ダッシュボード（sync:false） | anon/publishable 相当（公開鍵）。 |
| `SUPABASE_SERVICE_ROLE_KEY` | ダッシュボード（sync:false・**秘匿**） | service_role/secret 相当。RLS 迂回・バッチ専用。フロントに露出禁止。 |
| `SUPABASE_JWKS_URL` | ダッシュボード（sync:false） | `https://<PROJECT_REF>.supabase.co/auth/v1/.well-known/jwks.json`（§1.3）。 |
| `SUPABASE_DB_URL` | ダッシュボード（sync:false・**秘匿**） | DB 直結文字列（RLS を効かせるため）。 |
| `CORS_ORIGINS` | ダッシュボード（sync:false） | Vercel 本番ドメイン。カンマ区切りで複数可。 |
| `OPENAI_API_KEY` | ダッシュボード（sync:false・**秘匿**） | 予測・要約・FB・埋め込み用。統括が貼る。 |
| `BATCH_INTERNAL_TOKEN` | Blueprint `generateValue`（自動生成・**秘匿**） | NL-API-16/17 保護トークン。生成値を Supabase Vault にも登録（④）。 |

### Vercel（フロント Next.js）

| 変数名 | 説明 |
| --- | --- |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://<PROJECT_REF>.supabase.co`（認証のみに使用）。 |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | anon/publishable 相当。**service_role は絶対に置かない**。 |
| `NEXT_PUBLIC_API_BASE` | Render の API ベース URL（例 `https://namilog-api.onrender.com`）。 |

### Supabase Vault

| シークレット名 | 説明 |
| --- | --- |
| `BATCH_INTERNAL_TOKEN` | Render 生成値と**同一**を登録。pg_net が `X-Batch-Token` に載せる（`supabase/cron.sql`）。 |

### Google Cloud Console（OAuth・統括発行）

| 値 | 説明 |
| --- | --- |
| Client ID / Client Secret | Supabase Auth の Google プロバイダに登録（秘匿）。手順は `docs/GOOGLE_OAUTH.md`。 |

---

## ① Supabase クラウド

1. **プロジェクト作成**（統括）: リージョンは日本利用なら Tokyo(ap-northeast-1) を推奨。
   作成後、`Project Settings → API` から `Project URL` / `anon` / `service_role` を控える
   （新形式なら `sb_publishable_` / `sb_secret_`。対応は `docs/GOOGLE_OAUTH.md` 参照）。
   `Project Settings → Database` の Connection string を `SUPABASE_DB_URL` 用に控える。

2. **マイグレーション適用**（スキーマ＋RLS＋トリガー＋権限＋seed）。ローカルからリンクして push:

   ```bash
   cd ~/Desktop/namilog
   # Supabase CLI でクラウドプロジェクトにリンク（<PROJECT_REF> は控えた値）
   supabase link --project-ref <PROJECT_REF>
   # supabase/migrations/ を順に適用（0001_init.sql → 0002_grants.sql）
   supabase db push
   # factor_catalog 12 行の seed 投入（未適用なら）
   #   ダッシュボード SQL Editor に supabase/seed.sql を貼るか、psql で流す:
   #   psql "<SUPABASE_DB_URL>" -f supabase/seed.sql
   ```

   確認（12 行）:
   ```bash
   psql "<SUPABASE_DB_URL>" -c "select count(*) from public.factor_catalog;"   -- => 12
   ```

3. **Google プロバイダ設定**（統括）: ダッシュボード `Authentication → Providers → Google` を
   有効化し、Client ID / Secret を登録。`Authentication → URL Configuration` で:
   - **Site URL**: Vercel 本番 URL（③確定後に設定。例 `https://namilog.vercel.app`）
   - **Redirect URLs**: 同上を追加。
   Google Cloud Console 側の **承認済みリダイレクト URI** に
   `https://<PROJECT_REF>.supabase.co/auth/v1/callback` を登録（`docs/GOOGLE_OAUTH.md` §1）。

---

## ② Render（バックエンド FastAPI・Blueprint）

1. **Blueprint 接続**: Render ダッシュボード → `New → Blueprint` → 本リポジトリを選択。
   ルートの `render.yaml` を自動検出し、`namilog-api`（web / python / free / singapore）を作成。

2. **環境変数の設定**: `render.yaml` の `sync:false` の変数（上表）をサービスの
   `Environment` で設定する。`OPENAI_API_KEY` は統括がここに貼る（秘匿）。
   `BATCH_INTERNAL_TOKEN` は Blueprint が自動生成するので、`Environment` 画面で**生成値を控える**
   （④の Vault 登録で使う）。

3. **デプロイ確認**: ビルド（`pip install -e .`）→ 起動（`uvicorn ... --port $PORT`）が成功し、
   ヘルスチェック `/health` が緑になること。API ベース URL（例 `https://namilog-api.onrender.com`）を控える。

   ```bash
   curl -s https://namilog-api.onrender.com/health   # => {"status":"ok"}
   ```

> APP_ENV=production かつ SUPABASE_JWKS_URL 未設定だと、JWT 安全ガード（`assert_secure_jwt_config`）
> が起動を止める。JWKS_URL を必ず設定すること（§1.3・R3）。

---

## ③ Vercel（フロント Next.js）

1. **プロジェクト作成**（統括）: 本リポジトリを Import。`Root Directory` を **`frontend`** に設定
   （モノレポのため）。Framework は Next.js 自動検出。

2. **環境変数**: 上表の `NEXT_PUBLIC_*` を設定。`NEXT_PUBLIC_API_BASE` は②で控えた Render URL。

3. **デプロイ**: ビルド（`npm run build`）成功を確認。発行された本番ドメインを控え、
   **①③の Supabase 側 Site URL / Redirect URLs と `CORS_ORIGINS`（Render）に反映**する
   （相互参照のため、ドメイン確定後にこの2箇所を更新）。

---

## ④ cron.sql 適用と Vault 登録

`supabase/cron.sql` を Supabase の `SQL Editor`（または `supabase db execute`）で実行する。
プレースホルダ `<RENDER_SERVICE>` を Render の本番ホスト名へ置換してから実行すること。

1. **Vault にトークン登録**（②で控えた生成値。**この実値はコミット・Slack 禁止**）:

   ```sql
   -- 初回登録
   select vault.create_secret('<RENDER が生成した BATCH_INTERNAL_TOKEN>', 'BATCH_INTERNAL_TOKEN');
   -- 確認（値は表示しない）
   select name, created_at from vault.secrets where name = 'BATCH_INTERNAL_TOKEN';
   ```

2. **cron ジョブ登録**: `supabase/cron.sql` の拡張有効化と `cron.schedule(...)` 2件を実行。
   - 日次予測: `0 21 * * *`（毎朝 06:00 JST）
   - 週次ノート: `0 18 * * 6`（日曜 03:00 JST）

3. **確認**:

   ```sql
   select jobid, jobname, schedule, active from cron.job;                          -- 2件
   select * from cron.job_run_details order by start_time desc limit 5;            -- 実行履歴
   ```

> トークンはジョブ定義に平文で書かず、`vault.decrypted_secrets` 参照で `X-Batch-Token` に載せる
> （§7.2）。FastAPI 側は定数時間比較で照合し、不一致・未設定は 401（fail-closed）。

---

## ⑤ デプロイ後スモーク（ログイン → 体調入力 → ホーム）

1. **ヘルス**: `curl -s https://namilog-api.onrender.com/health` → `{"status":"ok"}`。
2. **未認証拒否**: `curl -s -o /dev/null -w "%{http_code}\n" https://namilog-api.onrender.com/api/home` → `401`。
3. **Google ログイン**: Vercel 本番 URL にアクセス → Google ログイン → オンボーディング
   （過去ログ→指標3選→免責同意）→ ホーム到達。
4. **体調入力**: 体調入力画面でスコア＋コメントを保存 → 履歴・ホームに反映されること。
5. **CORS**: ブラウザ DevTools で API 呼び出しに CORS エラーが出ないこと（`CORS_ORIGINS` に本番ドメインが含まれること）。
6. **バッチ疎通**（任意・手動起動で確認）: Vault 登録済みトークンで内部エンドポイントが通ること。
   ```bash
   # <TOKEN> は Vault/Render に設定した実値（コミット・Slack 禁止）。OPENAI_API_KEY 設定済みが前提。
   curl -s -X POST https://namilog-api.onrender.com/api/predictions/run \
     -H "X-Batch-Token: <TOKEN>" -H "Content-Type: application/json" -d '{}'
   # 誤トークンは 401 になること:
   curl -s -o /dev/null -w "%{http_code}\n" -X POST \
     https://namilog-api.onrender.com/api/predictions/run -H "X-Batch-Token: wrong" -d '{}'   # => 401
   ```

---

## 補足・運用メモ

- **タイムゾーン**: 日付判定（予測 target_date・週次ノートの週境界・未来日ガード）は
  アプリ側で JST（`app_today`＝明示 ZoneInfo）に統一済みで、**プロセス TZ 非依存**。Render が UTC で
  動いても正しい JST 日付で動作する（M4前半 QA Major-1 是正）。`TZ` 環境変数の設定は不要。
- **Render Free のスリープ**: 15 分無通信でスリープ→復帰約1分。朝の日次バッチが先に起こすため
  実害は限定的。初回待ちを消すなら Starter($7/月)へ無停止アップグレード可（`設計/ホスティング比較.md`）。
- **Supabase 一時停止回避**: 日次バッチが毎日 DB を触るため、無料枠の一時停止を追加コストゼロで回避（§7.5）。
- **ロールバック**: Render/Vercel はダッシュボードから前デプロイに戻せる。cron は
  `select cron.unschedule('namilog-daily-predictions');` 等で解除できる。

---

関連: `README.md` / `ARCHITECTURE.md`（§1.2 / §7.2 / §7.5.1）/ `docs/GOOGLE_OAUTH.md` /
`render.yaml` / `supabase/cron.sql` / [[リリース規定]] / [[セキュリティ規定]]。
