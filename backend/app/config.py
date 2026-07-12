"""アプリ設定。環境変数（backend/.env）から読み込む。

ローカル既定値は Supabase CLI（`supabase start`）の既定値に合わせてある。
本番では必ず環境変数で上書きする（特に JWT 検証は JWKS 方式を推奨）。
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # JWT 検証。ローカル既定は HS256 共有シークレット（Supabase CLI の既定値）。
    # 本番は JWKS（非対称鍵）を推奨。SUPABASE_JWKS_URL を設定すると JWKS 検証に切り替わる。
    supabase_jwt_secret: str = "super-secret-jwt-token-with-at-least-32-characters-long"
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


settings = Settings()
