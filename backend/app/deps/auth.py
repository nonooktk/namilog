"""Supabase JWT の検証（ARCHITECTURE.md §1.3）。

- ローカル既定は HS256 共有シークレット（Supabase CLI の既定 JWT secret）。
- 本番は JWKS（非対称鍵）を第一候補とする。SUPABASE_JWKS_URL を設定すると JWKS 検証に
  切り替わる（鍵ローテーション耐性のため）。

get_current_user は検証済み JWT の `sub`（= auth.uid() に一致する UUID）を返す。
未検証・欠落は 401 を返す。
"""
from __future__ import annotations

import jwt
from fastapi import Header, HTTPException, status

from ..config import settings

# JWKS クライアントは URL 設定時のみ生成（署名鍵をキャッシュ）
_jwk_client: jwt.PyJWKClient | None = None


def _get_jwk_client() -> jwt.PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = jwt.PyJWKClient(settings.supabase_jwks_url)
    return _jwk_client


def decode_token(token: str) -> dict:
    """JWT を検証してクレームを返す。失敗時は jwt 例外を送出する。"""
    if settings.supabase_jwks_url:
        signing_key = _get_jwk_client().get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            signing_key,
            algorithms=["RS256", "ES256"],
            audience=settings.jwt_audience,
            options={"verify_aud": True},
        )
    # HS256 共有シークレット（ローカル／後方互換）
    return jwt.decode(
        token,
        settings.supabase_jwt_secret,
        algorithms=["HS256"],
        audience=settings.jwt_audience,
        options={"verify_aud": True},
    )


async def get_current_user(authorization: str | None = Header(default=None)) -> str:
    """`Authorization: Bearer <JWT>` を検証し、ユーザー ID（sub）を返す。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証トークンがありません（Authorization: Bearer <JWT> が必要です）",
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = decode_token(token)
    except Exception as exc:  # noqa: BLE001 検証失敗はすべて 401 に集約
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"トークンの検証に失敗しました: {exc}",
        ) from exc
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="トークンに sub（ユーザー ID）が含まれていません",
        )
    return str(sub)
