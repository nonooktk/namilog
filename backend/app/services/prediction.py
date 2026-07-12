"""予測パイプライン（ARCHITECTURE.md §4）。

M3 で本実装（GPT-4o-mini 日次予測・類似日 few-shot・突合）。M2 は骨組みのみ。
実測登録時の予測突合（§4.4）はルーターの同一トランザクション内で行う（本ファイルではない）。
"""
from __future__ import annotations


async def run_daily_prediction(uid: str) -> None:  # pragma: no cover - M3 で実装
    """対象ユーザーの明日予測を生成し predictions に upsert する（NL-API-16）。"""
    raise NotImplementedError("日次予測は M3 で実装します")
