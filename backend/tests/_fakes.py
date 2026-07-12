"""テスト用フェイク（LLM / Open-Meteo）。

OPENAI_API_KEY 無しで本番コードパス（予測→突合→ノート更新・FB応答・埋め込み）を検証するための
決定的フェイク実装。`app.dependency_overrides` で本物のプロバイダに差し替えて使う。
"""
from __future__ import annotations

import hashlib
import struct
from typing import Any

EMBEDDING_DIM = 1536


def _deterministic_vector(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """テキストから決定的な埋め込みベクトルを生成する（同一テキスト→同一ベクトル）。

    ハッシュを種にした擬似乱数で dim 次元を埋める。完全一致テキストは距離0で最近傍になるため、
    類似日検索のテストに使える。
    """
    vec: list[float] = []
    counter = 0
    while len(vec) < dim:
        h = hashlib.sha256(f"{text}#{counter}".encode("utf-8")).digest()
        # 8バイトずつ float 化
        for i in range(0, len(h), 8):
            chunk = h[i : i + 8]
            if len(chunk) < 8:
                break
            (val,) = struct.unpack("<Q", chunk)
            vec.append((val % 20000) / 10000.0 - 1.0)  # [-1,1)
            if len(vec) >= dim:
                break
        counter += 1
    return vec[:dim]


class FakeLLMClient:
    """LLMClient プロトコルの決定的フェイク。"""

    def __init__(
        self,
        *,
        predicted_score: int = 6,
        crisis_flag: bool = False,
        advice: str = "水分をとってゆっくり過ごしましょう。",
        rationale: str = "直近の記録と外部指標を参考にした見立てです。",
        note_text: str = "・気圧が下がった翌日に落ち込みやすい傾向。\n・睡眠が短い週は不調が続きやすい。",
        reply_text: str = "教えてくれてありがとうございます。少しずつでも大丈夫です。",
    ) -> None:
        self.predicted_score = predicted_score
        self.crisis_flag = crisis_flag
        self.advice = advice
        self.rationale = rationale
        self.note_text = note_text
        self.reply_text = reply_text
        self.embed_calls: list[list[str]] = []
        self.json_calls: list[str] = []
        self.text_calls: list[str] = []

    async def complete_json(
        self, *, system: str, user: str, schema_name: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        self.json_calls.append(user)
        return {
            "predicted_score": self.predicted_score,
            "advice": self.advice,
            "rationale": self.rationale,
            "confidence": "medium",
            "crisis_flag": self.crisis_flag,
        }

    async def complete_text(self, *, system: str, user: str, max_tokens: int = 400) -> str:
        self.text_calls.append(user)
        # ノート更新か FB 応答かを system で大まかに判別（決定的な戻り値）。
        if "箇条書き" in system or "パターン" in system:
            return self.note_text
        return self.reply_text

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.embed_calls.append(list(texts))
        return [_deterministic_vector(t) for t in texts]


class FakeMeteoGetter:
    """MeteoGetter のフェイク。ネットワークを叩かず固定のレスポンスを返す。"""

    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload if payload is not None else _sample_meteo_payload()
        self.calls: list[tuple[str, dict]] = []

    async def get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((url, params))
        return self.payload


def _sample_meteo_payload() -> dict[str, Any]:
    """2日分の最小 Open-Meteo 応答（daily＋hourly）。"""
    return {
        "daily": {
            "time": ["2026-06-01", "2026-06-02"],
            "sunshine_duration": [36000.0, 18000.0],  # 秒 → 10h, 5h
            "temperature_2m_max": [28.0, 24.0],
            "temperature_2m_min": [18.0, 16.0],
            "weather_code": [1, 61],
        },
        "hourly": {
            "time": [
                "2026-06-01T00:00",
                "2026-06-01T12:00",
                "2026-06-02T00:00",
                "2026-06-02T12:00",
            ],
            "surface_pressure": [1013.0, 1011.0, 1005.0, 1003.0],
            "relative_humidity_2m": [60.0, 50.0, 80.0, 90.0],
        },
    }
