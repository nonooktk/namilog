"""外部依存（LLM／Open-Meteo）の提供者（依存性注入）。

FastAPI の `Depends` で解決し、テストでは `app.dependency_overrides` でフェイクへ差し替える。
これにより OPENAI_API_KEY 未設定でも本番コードパスをテストできる（品質基準・引き継ぎ）。
"""
from __future__ import annotations

from ..services.llm import LLMClient, build_llm_client
from ..services.openmeteo import HttpxMeteoGetter, MeteoGetter


def get_llm_client() -> LLMClient | None:
    """LLM クライアントを返す。OPENAI_API_KEY 未設定なら None（degrade）。"""
    return build_llm_client()


def get_meteo_getter() -> MeteoGetter:
    """Open-Meteo 取得クライアントを返す（鍵不要）。"""
    return HttpxMeteoGetter()
