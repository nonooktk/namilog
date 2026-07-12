"""RLS の独立検証（R5）。

アプリの `where user_id` フィルタに依存せず、DB の RLS 単体で越境が防げることを直検証する
（belt を見て suspenders も見る）。`user_tx` と同手順で claims/role を注入し、`where` 句なしの
生 SELECT や、他人 user_id を明示指定した越境試行が RLS で 0 件になることを確認する。
"""
from __future__ import annotations

import json

import psycopg

from conftest import requires_stack


def _count_as_user(db_url: str, sub: str, sql: str, params: tuple = ()) -> int:
    """user_tx と同じ手順（claims + role=authenticated）で SELECT し、先頭カラムを返す。"""
    with psycopg.connect(db_url) as conn:
        with conn.transaction():
            conn.execute(
                "select set_config('request.jwt.claims', %s, true)",
                (json.dumps({"sub": sub, "role": "authenticated"}),),
            )
            conn.execute("select set_config('role', 'authenticated', true)")
            return conn.execute(sql, params).fetchone()[0]


def _scalar_as_postgres(db_url: str, sql: str, params: tuple = ()):
    """postgres（RLS 迂回・BYPASSRLS）で実行。行が実在することの確認に使う。"""
    with psycopg.connect(db_url) as conn:
        return conn.execute(sql, params).fetchone()[0]


@requires_stack
def test_rls_blocks_cross_user_without_app_filter(client, user_a, user_b, db_url):
    a_id, b_id = user_a["id"], user_b["id"]

    # A が識別可能な記録を作る（アプリ経由）
    r = client.post(
        "/api/records",
        headers=user_a["headers"],
        json={"record_date": "2026-01-20", "actual_score": 5, "comment": "RLS-probe-A"},
    )
    assert r.status_code == 201

    # 行は DB に実在する（postgres は RLS 迂回で見える）
    assert _scalar_as_postgres(
        db_url, "select count(*) from public.daily_records where comment=%s", ("RLS-probe-A",)
    ) >= 1

    # A の claims では自分の行が見える
    assert _count_as_user(
        db_url, a_id, "select count(*) from public.daily_records where comment=%s", ("RLS-probe-A",)
    ) == 1

    # B の claims では where 句なしでも A の行は一切見えない（RLS 単体で越境拒否）
    assert _count_as_user(
        db_url, b_id, "select count(*) from public.daily_records where comment=%s", ("RLS-probe-A",)
    ) == 0

    # B が A の user_id を明示指定して越境を試みても 0（user_id 詐称を RLS が封じる）
    assert _count_as_user(
        db_url, b_id, "select count(*) from public.daily_records where user_id=%s", (a_id,)
    ) == 0

    # 実行ロールは authenticated（superuser でなく、BYPASSRLS でない）
    assert _count_as_user(db_url, b_id, "select current_user") == "authenticated"
    assert _count_as_user(
        db_url, b_id, "select rolbypassrls from pg_roles where rolname = current_user"
    ) is False
