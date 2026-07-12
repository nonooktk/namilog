# なみログ backend（FastAPI）

全データアクセスの入口。Supabase JWT を検証し、ユーザー文脈で DB にアクセスして RLS を効かせる。

## 構成

```
app/
├── main.py            # エントリポイント・ルーター登録・CORS
├── config.py          # 設定（backend/.env）
├── db.py              # DB 接続。user_tx（RLS 有効）/ service_tx（バッチ・RLS 迂回）
├── deps/auth.py       # Supabase JWT 検証（HS256 共有シークレット / JWKS）
├── schemas.py         # pydantic スキーマ（バリデーション）
├── deps/batch.py      # バッチ内部トークン検証（X-Batch-Token）
├── deps/providers.py  # LLM / Open-Meteo の依存性注入（テストでフェイクに差し替え）
├── routers/           # profile / records / factors / home / history / feedback / predictions / notes
└── services/          # prediction / notes / openmeteo / embeddings / crisis / guardrails / llm / support_messages
```

## 実装済み API（M2 + M3）

| API-ID | メソッド / パス | 概要 |
| --- | --- | --- |
| NL-API-01 | GET/PUT `/api/profile` | プロフィール取得・更新（医療免責同意） |
| NL-API-02 | POST `/api/records/bulk` | 過去ログ一括入力 |
| NL-API-03 | GET `/api/factors/catalog` | 12 指標マスタ |
| NL-API-04/12 | PUT `/api/factors/selection` | 3指標の選定・入れ替え（行は消さない切替） |
| NL-API-11 | GET `/api/factors/selection` | 現在の選択＋履歴 |
| NL-API-05 | GET `/api/home` | 本日/明日の予測・実測（予測未生成なら degrade） |
| NL-API-06 | POST `/api/records` | 実測登録＋予測突合＋危機検知 |
| NL-API-07 | PUT `/api/records/{record_date}` | 実測修正＋予測突合 |
| NL-API-08 | PUT `/api/factor-values/{value_date}` | 手入力指標値の JSONB マージ |
| NL-API-09 | GET `/api/records?from=&to=` | 履歴一覧（実測・予測結合） |
| NL-API-10 | GET `/api/history/series?from=&to=` | 波グラフ用時系列 |
| NL-API-13 | POST `/api/factors/suggest` | AI 入れ替え提案（提案キー＋理由・採否は本人） |
| NL-API-14 | GET `/api/feedback?prediction_id=&limit=` | FB チャット履歴取得 |
| NL-API-15 | POST `/api/feedback` | user 発話→GPT 応答→保存（発話も危機検知の入力源） |
| NL-API-16 | POST `/api/predictions/run` | 日次予測バッチ（**内部トークン** X-Batch-Token 必須） |
| NL-API-17 | POST `/api/notes/refresh` | 週次ノート更新バッチ（**内部トークン**必須） |
| NL-API-18 | GET `/api/notes/current` | 現行の予測ノート取得 |

未認証は全 API で 401。バッチ（16/17）は `X-Batch-Token` ヘッダ（`BATCH_INTERNAL_TOKEN`）で保護し、
未設定・不一致は 401（fail-closed）。`/health` は認証不要の疎通確認。

## M3 の外部依存と「実キー」について（重要・引き継ぎ）

- **OpenAI（`OPENAI_API_KEY`）**: 日次予測（GPT-4o-mini・構造化出力）・コメント要約・FB 応答・
  埋め込み（text-embedding-3-small）に使用。**キー未設定でも起動・pytest は通る**（LLM 機能のみ
  degrade）。クライアントは `services/llm.py` で抽象化し、テストはフェイク（`tests/_fakes.py`）を
  `app.dependency_overrides` で注入して検証している。**実キーでの GPT 動作確認は統括のキー提供後に
  実施する。現時点で「実 GPT 確認済み」とは記録していない。**
- **Open-Meteo（鍵不要）**: 気圧・日照・寒暖差・天候/湿度を取得し `factor_values` に日次マージ。
  疎通テスト（`tests/test_openmeteo.py::test_live_openmeteo_smoke`）のみ実 API を叩く（ネットワーク
  不通時は skip）。それ以外はフェイク getter でモック。
- **バッチ運用**: `POST /api/predictions/run`・`/api/notes/refresh` はスケジューラ（Render Cron 等・
  ホスティング選定は §9-1）から `X-Batch-Token: <BATCH_INTERNAL_TOKEN>` を付けて叩く。
- **危機検知の窓口文言**: `services/support_messages.py` の定数に集約（マイメロディ／シナモロールの
  確定待ち・暫定表示）。確定後はこの1定数を差し替えれば全経路へ反映される。
- **低スコア連続トリガー**: `services/crisis.py` の閾値は暫定（§9-2 で確定）。TODO を明記。

## 起動

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # 値は supabase start の出力を設定（.env はコミット禁止）
uvicorn app.main:app --reload --port 8000
```

## テスト

`pytest` は2モードでテストユーザーを用意する（`tests/conftest.py`）。

- **Mode A（本物）**: `supabase start` 済みなら `supabase status` から接続情報を取り、GoTrue で
  ユーザー作成→サインインして実 JWT を得る。
- **Mode B（Docker ハーネス）**: Supabase CLI が使えない環境向け。`tests/_harness/supabase_shim.sql`
  で Supabase 相当の auth（ロール・auth スキーマ・`auth.uid()`/`auth.role()`）を再現した Postgres を
  用意し、環境変数で指す。

```bash
# Mode B の例（pgvector 入り Postgres を Docker で用意）
docker run -d --name namilog-test-db -e POSTGRES_PASSWORD=postgres \
  -p 54329:5432 pgvector/pgvector:pg16
docker exec -i namilog-test-db psql -U postgres < tests/_harness/supabase_shim.sql
docker exec -i namilog-test-db psql -U postgres < ../supabase/migrations/0001_init.sql
docker exec -i namilog-test-db psql -U postgres < ../supabase/seed.sql

export NAMILOG_TEST_DB_URL="postgresql://postgres:postgres@127.0.0.1:54329/postgres"
pytest -v
```

どちらのモードも成立しなければ、DB を要するテストは自動スキップ（未認証 401 等は常に実行）。
