# Google ログイン（Supabase Auth）設定手順

なみログのログインは Supabase Auth の Google プロバイダで行います（ARCHITECTURE.md §1.3）。
本ドキュメントはローカル開発と本番での設定手順をまとめます。

> [!important] 統括への依頼事項
> Google OAuth の **Client ID / Client Secret** は Google Cloud Console で発行する秘匿情報です
> （[[セキュリティ規定]]）。M2 では発行しておらず、Google ログインの E2E 検証は未実施です。
> クレデンシャルは統括が用意し、安全な経路で共有してください（コミット・Slack 投稿は禁止）。
> M2 のローカル検証は開発専用ユーザー（email/password）で JWT 発行→API 検証まで実施済みです。

## 1. Google Cloud Console でクレデンシャルを発行

1. Google Cloud Console → 「API とサービス」→「認証情報」→「OAuth クライアント ID を作成」。
2. アプリの種類: **ウェブ アプリケーション**。
3. **承認済みのリダイレクト URI** に Supabase のコールバックを登録:
   - ローカル: `http://127.0.0.1:54321/auth/v1/callback`
   - 本番: `https://<PROJECT_REF>.supabase.co/auth/v1/callback`
4. 発行された **Client ID** と **Client Secret** を控える（秘匿。`.env` 管理）。

## 2. ローカル（Supabase CLI）での有効化

`supabase/config.toml` の Google プロバイダ設定を有効にします（値は環境変数から注入し、
平文で config に書かない）。

```toml
[auth.external.google]
enabled = true
client_id = "env(SUPABASE_AUTH_GOOGLE_CLIENT_ID)"
secret = "env(SUPABASE_AUTH_GOOGLE_SECRET)"
redirect_uri = "http://127.0.0.1:54321/auth/v1/callback"
```

```bash
# .env（コミット禁止）に設定してから
export SUPABASE_AUTH_GOOGLE_CLIENT_ID=...   # 秘匿
export SUPABASE_AUTH_GOOGLE_SECRET=...      # 秘匿
supabase start   # 反映
```

フロントからは `lib/supabase.ts` の `signInWithGoogle()` でログインを開始します。

## 3. 本番（Supabase クラウド）での有効化

> クラウドプロジェクトの作成は統括承認後（M2 の制約によりローカルのみ）。

1. Supabase ダッシュボード → Authentication → Providers → Google を有効化。
2. Client ID / Secret を登録。
3. フロントの `Site URL` / `Redirect URLs` に本番ドメイン（Vercel）を登録。

## 4. 開発専用ユーザー（email/password）でのローカル検証

Google クレデンシャルが未発行でも、API の JWT 検証・RLS はローカル検証できます。

```bash
# ユーザー作成（GoTrue admin API。service_role 鍵を使用＝ローカル限定・秘匿）
curl -s "$SUPABASE_URL/auth/v1/admin/users" \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"email":"dev@example.com","password":"dev-Password-123!","email_confirm":true}'

# サインインして access_token(JWT) を取得
curl -s "$SUPABASE_URL/auth/v1/token?grant_type=password" \
  -H "apikey: $SUPABASE_ANON_KEY" -H "Content-Type: application/json" \
  -d '{"email":"dev@example.com","password":"dev-Password-123!"}'

# 取得した access_token を Bearer に付けて API を叩く
curl -s http://localhost:8000/api/profile -H "Authorization: Bearer <access_token>"
```

> このユーザーは **開発専用**。本番では使わないこと（[[セキュリティ規定]] 権限最小化）。
