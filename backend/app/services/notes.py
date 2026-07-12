"""予測ノートの週次更新（ARCHITECTURE.md §4.3）。M3 で本実装。M2 は骨組みのみ。"""
from __future__ import annotations


async def refresh_weekly_note(uid: str) -> None:  # pragma: no cover - M3 で実装
    """直近実績・FB から本人固有の知見を抽出し、新版ノートを作成して current 切替（NL-API-17）。"""
    raise NotImplementedError("週次ノート更新は M3 で実装します")
