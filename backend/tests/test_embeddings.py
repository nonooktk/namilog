"""埋め込み・類似日検索のテスト（§2.10 / §4.1）。

bulk 投入（フェイク LLM でバッチ埋め込み）→ pgvector 類似日検索が本人スコープ・未来リーク防止で
最近傍を返すことを検証する。
"""
from __future__ import annotations

import asyncio
from datetime import date

from conftest import requires_stack


@requires_stack
def test_bulk_embeds_and_similar_search(client, user_a, use_fakes, db_url):
    use_fakes()  # フェイク LLM を注入（bulk で埋め込みがバッチ生成される）
    h = user_a["headers"]
    r = client.post(
        "/api/records/bulk",
        headers=h,
        json={
            "records": [
                {"record_date": "2026-04-10", "actual_score": 4, "comment": "頭痛がつらい"},
                {"record_date": "2026-04-11", "actual_score": 7, "comment": "よく眠れて快調"},
                {"record_date": "2026-04-12", "actual_score": 5, "comment": "気圧が低い一日"},
            ]
        },
    )
    assert r.status_code == 201

    # 「頭痛がつらい」の埋め込み（フェイクは同一テキスト→同一ベクトル）で類似検索すると当該日が最近傍。
    # 注: TestClient のイベントループと分離するため、アプリのプールではなく専用接続を使う
    #     （user_tx と同じ手順で RLS claims を張る）。
    import json

    import psycopg
    from psycopg.rows import dict_row

    from _fakes import _deterministic_vector
    from app.services import embeddings

    uid = user_a["id"]

    async def run():
        conn = await psycopg.AsyncConnection.connect(
            db_url, autocommit=True, row_factory=dict_row
        )
        try:
            async with conn.transaction():
                await conn.execute(
                    "select set_config('request.jwt.claims', %s, true)",
                    (json.dumps({"sub": uid, "role": "authenticated"}),),
                )
                await conn.execute("select set_config('role', 'authenticated', true)")
                qvec = _deterministic_vector("頭痛がつらい")
                return await embeddings.find_similar_dates(
                    conn, uid, qvec, date(2026, 5, 1), k=3
                )
        finally:
            await conn.close()

    rows = asyncio.run(run())
    assert rows, "類似日が取得できませんでした"
    # 完全一致テキストの日が最近傍（距離ほぼ0）で先頭に来る。
    assert rows[0]["comment"] == "頭痛がつらい"
    assert rows[0]["distance"] < 1e-6
    # 未来リーク防止: today(2026-05-01) 以降は含まれない。
    assert all(row["record_date"] < date(2026, 5, 1) for row in rows)
