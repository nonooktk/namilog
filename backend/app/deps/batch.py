"""バッチ内部エンドポイント（NL-API-16/17）の保護（ARCHITECTURE.md §7.2・推奨B）。

NL-API-16/17 は `/api` 配下の到達可能なエンドポイントであり、認証が甘いと他人の予測バッチを
外部から起動されうる。`BATCH_INTERNAL_TOKEN` を固定ヘッダ `X-Batch-Token` で照合し、一致しなければ
401 を返す。トークンはユーザー JWT とは別系統でスケジューラ側に秘匿設定する。

セキュリティ上の注意:
  - トークンが未設定（空）のまま本番でバッチを開けると誰でも叩けてしまうため、**未設定なら常に 401**
    にする（fail-closed）。ローカルでバッチをテストするときは .env に開発用トークンを設定する。
  - 比較は定数時間比較（hmac.compare_digest）でタイミング攻撃を避ける。
"""
from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from ..config import settings


async def verify_batch_token(x_batch_token: str | None = Header(default=None)) -> None:
    """`X-Batch-Token` ヘッダを検証する。不一致・未設定は 401（fail-closed）。"""
    expected = settings.batch_internal_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="バッチトークンが未設定です（BATCH_INTERNAL_TOKEN を設定してください）",
        )
    if not x_batch_token or not hmac.compare_digest(x_batch_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="バッチトークンが不正です",
        )
