# なみログ（namilog）

体調の波を客観指標で予測し、やさしく注意喚起する体調記録アプリ。

- 設計正本: `../toolmaker/02_プロジェクト/namilog/ARCHITECTURE.md`（キャタピー）
- 要件・受け入れ条件: `../toolmaker/02_プロジェクト/namilog/README.md`
- 実装計画: `../toolmaker/02_プロジェクト/namilog/IMPLEMENTATION_PLAN.md`

> [!warning] 医療行為ではありません
> 本アプリは診断・治療などの医療行為ではなく、参考情報を提供するものです。

## 構成

```
namilog/
├── frontend/   # Next.js（App Router / TypeScript）。認証と画面。DB は直読みしない（P-1）
│   └── lib/    # api.ts（FastAPI クライアント）/ supabase.ts（Auth のみ）
├── backend/    # FastAPI。全データアクセスの入口・JWT 検証・予測（M3）
│   └── app/    # main.py / db.py / deps/auth.py / routers/ / services/
├── supabase/   # DB 定義（版管理）
│   ├── migrations/0001_init.sql  # 全テーブル＋RLS＋インデックス＋profiles 自動生成トリガー
│   └── seed.sql                   # factor_catalog 12 行
└── docs/       # GOOGLE_OAUTH.md（Google ログイン設定手順）
```

## アーキテクチャ要点

- **データアクセスは FastAPI 経由に一本化**（P-1）。フロントは Supabase を直読みしない。
- **RLS で「本人の行のみ read/write」を DB 層で強制**（P-2）。
- **外部指標は不変の論理キー `factor_key` で JSONB に全件蓄積**（P-3）。12→3 の入れ替えでも過去の紐付けが切れない。
- **予測と実測の突合は明示ステップ**（P-4）。実測登録時に同一トランザクションで誤差を記録。

## ローカル開発手順

前提: Docker Desktop 起動済み、Node 20+、Python 3.11+、Supabase CLI。

```bash
# 1) Supabase をローカル起動（本番と同一スキーマ/RLS を Docker で再現）
cd ~/Desktop/namilog
supabase start                # API URL / anon key / service_role key / DB URL を控える
supabase db reset             # migrations 適用 → seed 投入

# 2) 環境変数（.env はコミットしない）
cp backend/.env.example backend/.env      # SUPABASE_* / SUPABASE_JWT_SECRET を設定
cp frontend/.env.example frontend/.env    # NEXT_PUBLIC_SUPABASE_* / NEXT_PUBLIC_API_BASE

# 3) バックエンド（FastAPI）
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000   # http://localhost:8000/health

# 4) フロント（別ターミナル）
cd ~/Desktop/namilog/frontend
npm install
npm run dev                   # http://localhost:3000
```

### テスト

```bash
cd backend && source .venv/bin/activate
pytest                        # Supabase ローカル or ハーネスDB があれば統合テストも走る
```

- Supabase CLI が使えない環境向けに、Docker の Postgres（pgvector）で Supabase 相当の auth を
  再現して検証するハーネスを同梱（`backend/tests/_harness/`）。詳細は `backend/README.md`。

## Google ログイン

`docs/GOOGLE_OAUTH.md` を参照。Client ID / Secret は統括が用意する秘匿情報で、コミット禁止。

## セキュリティ

- `.env`・秘匿値は絶対にコミットしない。`.env.example` は空。
- `service_role` 鍵はバックエンド専用。フロントに露出させない。
