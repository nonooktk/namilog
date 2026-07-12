"""埋め込み・類似日検索（ARCHITECTURE.md §2.10 / §4.1）。

text-embedding-3-small（1536次元）でコメントを埋め込み、pgvector で本人スコープの類似日を
検索して few-shot に投入する。**類似日検索は必ず `where user_id = :uid`** で絞る（§7.1）。

方針:
  - bulk 投入時は配列入力でバッチ化（M1 推奨A）＝ `client.embed([...])` を1回で叩く。
  - 埋め込み保存はベストエフォート。LLM クライアント未設定（OPENAI_API_KEY 無し）や失敗時は
    保存をスキップし、本体の書き込み（体調記録）は壊さない（§7.5 の degrade 思想）。
"""
from __future__ import annotations

from datetime import date
from typing import Any, Sequence

from .llm import LLMClient

EMBEDDING_DIM = 1536


def _to_vector_literal(vec: Sequence[float]) -> str:
    """pgvector のテキスト表現（'[v1,v2,...]'）へ変換する。"""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


async def embed_and_store(
    conn,
    uid: str,
    items: Sequence[tuple[str, date, str | None]],
    client: LLMClient | None,
) -> int:
    """(daily_record_id, record_date, comment) 群の埋め込みをまとめて生成・保存する。

    - コメントが空の項目は対象外（埋め込む意味がないため）。
    - `client` が None なら 0 件（degrade）。呼び出し側は失敗しても本体書き込みを継続する。
    - `comment_embeddings` は daily_record_id 一意 → upsert（再入力時は最新へ更新）。
    返り値: 保存した件数。
    """
    if client is None:
        return 0
    targets = [(rid, rdate, (c or "").strip()) for rid, rdate, c in items if (c or "").strip()]
    if not targets:
        return 0

    # バッチ化: コメント配列を1リクエストで埋め込む（M1 推奨A）。
    vectors = await client.embed([c for _, _, c in targets])
    if len(vectors) != len(targets):
        # 想定外の不一致時は保存しない（誤対応で他日の埋め込みを紐付ける事故を防ぐ）。
        return 0

    count = 0
    for (rid, rdate, _comment), vec in zip(targets, vectors):
        await conn.execute(
            """
            insert into public.comment_embeddings
                (user_id, daily_record_id, record_date, embedding)
            values (%(uid)s, %(rid)s, %(rdate)s, %(vec)s::vector)
            on conflict (daily_record_id)
            do update set embedding = excluded.embedding,
                          record_date = excluded.record_date,
                          created_at = now()
            """,
            {"uid": uid, "rid": rid, "rdate": rdate, "vec": _to_vector_literal(vec)},
        )
        count += 1
    return count


async def find_similar_dates(
    conn,
    uid: str,
    qvec: Sequence[float],
    today: date,
    *,
    k: int = 3,
) -> list[dict[str, Any]]:
    """当日コメントの埋め込み qvec で、本人の過去類似日を pgvector 検索する（§4.1）。

    - `where ce.user_id = :uid`（本人スコープ厳守）。
    - `dr.record_date < :today`（未来リーク防止）。
    - cosine 近傍 top-k。
    """
    cur = await conn.execute(
        """
        select dr.record_date, dr.actual_score, dr.comment,
               (ce.embedding <=> %(qvec)s::vector) as distance
        from public.comment_embeddings ce
        join public.daily_records dr on dr.id = ce.daily_record_id
        where ce.user_id = %(uid)s
          and dr.record_date < %(today)s
        order by ce.embedding <=> %(qvec)s::vector
        limit %(k)s
        """,
        {"uid": uid, "qvec": _to_vector_literal(qvec), "today": today, "k": k},
    )
    return await cur.fetchall()
