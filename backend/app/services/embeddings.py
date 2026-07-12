"""埋め込み・類似日検索（ARCHITECTURE.md §2.10 / §4.1）。M3 で本実装。M2 は骨組みのみ。

text-embedding-3-small（1536次元）でコメントを埋め込み、pgvector で本人スコープの
類似日を検索して few-shot に投入する。類似日検索は必ず `where user_id = :uid` で絞る。
"""
from __future__ import annotations


async def embed_and_store(uid: str, daily_record_id: str, comment: str) -> None:  # pragma: no cover - M3
    raise NotImplementedError("埋め込み生成は M3 で実装します")
