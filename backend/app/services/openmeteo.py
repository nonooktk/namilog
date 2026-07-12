"""Open-Meteo 外部指標取得（ARCHITECTURE.md §5.1）。M3 で本実装。M2 は骨組みのみ。

鍵不要・無料。profiles.latitude/longitude（粗い座標）で気圧・日照・寒暖差・天候/湿度を取得し
factor_values.values にマージする。
"""
from __future__ import annotations


async def fetch_daily_factors(lat: float, lon: float, tz: str) -> dict:  # pragma: no cover - M3
    raise NotImplementedError("Open-Meteo 連携は M3 で実装します")
