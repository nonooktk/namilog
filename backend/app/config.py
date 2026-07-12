"""アプリ設定。環境変数（backend/.env）から読み込む。

ローカル既定値は Supabase CLI（`supabase start`）の既定値に合わせてある。
本番では必ず環境変数で上書きする（特に JWT 検証は JWKS 方式を推奨）。
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

# Supabase CLI がローカルで用いる既知の既定 JWT シークレット。
# 本番でこれが使われていると、既定シークレットで署名した偽トークンを受理してしまう（認証バイパス）。
DEFAULT_LOCAL_JWT_SECRET = "super-secret-jwt-token-with-at-least-32-characters-long"

# 認証不要で「安全でない JWT 構成」を許すのはローカル/テスト系の環境のみ。
_LOCAL_ENVS = {"local", "test", "testing", "dev", "development"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Supabase ローカル既定（`supabase start` の既定値）
    supabase_url: str = "http://127.0.0.1:54321"
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    # RLS を効かせるため postgres で接続し、リクエストごとに role/JWT claims を設定する
    supabase_db_url: str = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"

    # 実行環境。"local"（既定）/ "test" 等ではローカル向け設定を許容し、それ以外
    # （"production" / "staging" など）では JWT 構成の安全性を起動時に強制する（R3）。
    app_env: str = "local"

    # JWT 検証。ローカル既定は HS256 共有シークレット（Supabase CLI の既定値）。
    # 本番は JWKS（非対称鍵）を推奨。SUPABASE_JWKS_URL を設定すると JWKS 検証に切り替わる。
    supabase_jwt_secret: str = DEFAULT_LOCAL_JWT_SECRET
    supabase_jwks_url: str = ""
    jwt_audience: str = "authenticated"

    cors_origins: str = "http://localhost:3000"

    # バッチ用内部エンドポイント（NL-API-16/17・M3）を保護する内部トークン。
    # 秘匿値。cron 呼び出し側と共有する（コミット禁止・.env 管理。§7.2）。
    batch_internal_token: str = ""

    # M3 で使用
    openai_api_key: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def assert_secure_jwt_config(self) -> None:
        """本番系での安全でない JWT 構成を起動時に拒否する（R3・セキュリティ規定4 / §1.3・§7.2）。

        非ローカル環境（production / staging 等）では、次のいずれかを必須とする:
          - JWKS（非対称鍵）検証（SUPABASE_JWKS_URL 設定）、または
          - Supabase 既定でない自前の HS256 シークレット（SUPABASE_JWT_SECRET 上書き）。
        既定シークレットのまま本番起動しようとすると RuntimeError で起動を止める
        （Supabase CLI の既知シークレットで署名した偽トークンの受理＝認証バイパスを防ぐ）。
        """
        if self.app_env.strip().lower() in _LOCAL_ENVS:
            return
        if self.supabase_jwks_url:
            return
        if not self.supabase_jwt_secret or self.supabase_jwt_secret == DEFAULT_LOCAL_JWT_SECRET:
            raise RuntimeError(
                f"APP_ENV={self.app_env!r} では JWT 検証が安全に構成されていません。"
                "SUPABASE_JWKS_URL を設定するか、SUPABASE_JWT_SECRET を Supabase 既定値以外に"
                "上書きしてください（既定シークレットによる認証バイパスの防止）。"
            )


settings = Settings()
