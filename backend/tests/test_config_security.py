"""本番 JWT 構成の起動時ガード（R3）。DB 不要のユニットテスト。"""
from __future__ import annotations

import pytest

from app.config import DEFAULT_LOCAL_JWT_SECRET, Settings


def test_local_env_allows_default_secret():
    """local 環境では既定シークレットでも起動可（開発利便）。"""
    Settings(app_env="local", supabase_jwt_secret=DEFAULT_LOCAL_JWT_SECRET,
             supabase_jwks_url="").assert_secure_jwt_config()


def test_test_env_allows_default_secret():
    Settings(app_env="test", supabase_jwt_secret=DEFAULT_LOCAL_JWT_SECRET,
             supabase_jwks_url="").assert_secure_jwt_config()


def test_production_default_secret_rejected():
    """本番で既定シークレットのままなら起動を拒否（認証バイパス防止）。"""
    s = Settings(app_env="production", supabase_jwt_secret=DEFAULT_LOCAL_JWT_SECRET,
                 supabase_jwks_url="")
    with pytest.raises(RuntimeError):
        s.assert_secure_jwt_config()


def test_production_empty_secret_rejected():
    s = Settings(app_env="production", supabase_jwt_secret="", supabase_jwks_url="")
    with pytest.raises(RuntimeError):
        s.assert_secure_jwt_config()


def test_production_with_jwks_ok():
    """本番でも JWKS 設定があれば起動可。"""
    Settings(app_env="production",
             supabase_jwks_url="https://example.supabase.co/auth/v1/.well-known/jwks.json"
             ).assert_secure_jwt_config()


def test_production_with_custom_secret_ok():
    """本番でも既定以外の自前シークレットなら起動可。"""
    Settings(app_env="production",
             supabase_jwt_secret="a-strong-non-default-secret-value-32chars!!",
             supabase_jwks_url="").assert_secure_jwt_config()
