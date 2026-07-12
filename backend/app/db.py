"""DB 接続（Supabase Postgres）。

設計方針（ARCHITECTURE.md §1.3 / §7.1）:
  - 通常の API はユーザー JWT 文脈（role=authenticated ＋ request.jwt.claims）で
    トランザクションを張り、RLS を DB 層で効かせる（P-2）。
  - バッチ処理（M3 の日次予測・週次ノート）だけは service（postgres 直＝RLS 迂回）で
    実行し、必ず `where user_id = :uid` を明示する（P-2/P-4）。

RLS を直結接続で効かせる仕組み:
  postgres（superuser, BYPASSRLS）で接続したうえで、トランザクション内に限り
  `SET LOCAL request.jwt.claims = '{"sub": <uid>, "role": "authenticated"}'` と
  `SET LOCAL ROLE authenticated` を設定する。これにより Supabase の `auth.uid()` /
  `auth.role()` が当該ユーザーを返し、authenticated ロールに RLS が適用される。
  トランザクション終了で自動的に元へ戻る（SET LOCAL のスコープ）。
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import AsyncIterator

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .config import settings

_pool: AsyncConnectionPool | None = None


async def get_pool() -> AsyncConnectionPool:
    """接続プールを遅延生成する（DB 不在でもアプリ自体は起動できるようにするため）。"""
    global _pool
    if _pool is None:
        pool = AsyncConnectionPool(
            conninfo=settings.supabase_db_url,
            min_size=1,
            max_size=10,
            open=False,
            # autocommit=True にしておき、トランザクション境界は conn.transaction() で明示する。
            # これにより user_tx / service_tx の BEGIN..COMMIT が明確になり、SET LOCAL（role /
            # request.jwt.claims）が確実に当該トランザクション内だけに閉じる（接続プールへのリーク防止）。
            kwargs={"row_factory": dict_row, "autocommit": True},
        )
        await pool.open(wait=True, timeout=10)
        _pool = pool
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def user_tx(uid: str) -> AsyncIterator[AsyncConnection]:
    """ユーザー JWT 文脈のトランザクション。RLS が効く（本人の行のみ read/write）。"""
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.transaction():
            claims = json.dumps({"sub": uid, "role": settings.jwt_audience})
            # 先に claims をセットしてから role を切り替える。
            await conn.execute(
                "select set_config('request.jwt.claims', %s, true)", (claims,)
            )
            await conn.execute("select set_config('role', 'authenticated', true)")
            yield conn


@asynccontextmanager
async def service_tx() -> AsyncIterator[AsyncConnection]:
    """service（postgres 直・RLS 迂回）トランザクション。

    バッチ用途（M3）。呼び出し側で必ず `where user_id = :uid` を明示すること（P-2）。
    M2 ではテスト補助・共有マスタ参照などに限定して使う。
    """
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.transaction():
            yield conn
