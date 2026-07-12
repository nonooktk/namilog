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
├── routers/           # profile / records / factors / home / history
└── services/          # prediction / notes / openmeteo / embeddings / crisis（M3 で本実装）
```

## 実装済み API（M2）

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

未認証は全 API で 401。`/health` は認証不要の疎通確認。

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
