"""OpenAI クライアントの抽象化（ARCHITECTURE.md §4 / §2.10 / §7.6）。

方針:
  - サービス／ルーターは具体的な OpenAI SDK ではなく、この `LLMClient` プロトコルに依存する。
    これにより OPENAI_API_KEY 未設定でもテストはフェイク実装で通せる（依存性注入。品質基準）。
  - 実 API 実装 `OpenAIClient` は追加依存を避けるため httpx（既存依存）で REST を直接叩く。
  - `build_llm_client()` は API キー未設定なら None を返す。呼び出し側は None のとき LLM 機能を
    degrade する（§7.5「外部障害の影響を局所化」）。バッチ予測など LLM 必須の経路は明示的に
    「未設定」を扱う。

注意（セキュリティ規定1・§7.2）:
  - OPENAI_API_KEY は settings 経由（.env）でのみ受け取り、ログ・例外メッセージに出さない。
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import httpx

from ..config import settings


@runtime_checkable
class LLMClient(Protocol):
    """予測・要約・FB 応答・埋め込みに必要な最小インタフェース。

    実装（実 OpenAI／フェイク）はこのプロトコルを満たせばよい。サービス層はこれにのみ依存する。
    """

    async def complete_json(
        self, *, system: str, user: str, schema_name: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        """構造化出力（JSON スキーマ・strict）でチャット補完を行い、dict を返す（§4.2）。"""
        ...

    async def complete_text(
        self, *, system: str, user: str, max_tokens: int = 400, model: str | None = None
    ) -> str:
        """自由記述のチャット補完（コメント要約・FB 応答）。テキストを返す。"""
        ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """テキスト配列をまとめて埋め込む（バッチ化＝M1 推奨A）。順序は入力と一致する。"""
        ...


class OpenAIClient:
    """OpenAI REST を httpx で叩く実クライアント（追加依存を増やさない）。

    実キーでの疎通確認は統括のキー提供後に行う（README/引き継ぎに明記）。キー無しで
    「実 GPT 確認済み」とは記録しない。
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        chat_model: str | None = None,
        embed_model: str | None = None,
        timeout: float | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAIClient には API キーが必要です")
        self._api_key = api_key
        self._base_url = (base_url or settings.openai_base_url).rstrip("/")
        self._chat_model = chat_model or settings.openai_chat_model
        self._embed_model = embed_model or settings.openai_embed_model
        self._timeout = timeout if timeout is not None else settings.external_http_timeout
        # http_client を注入できるようにして、テストでは httpx.MockTransport 等を差し込める。
        self._external_client = http_client

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        if self._external_client is not None:
            resp = await self._external_client.post(
                url, headers=self._headers(), json=payload
            )
            resp.raise_for_status()
            return resp.json()
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
            resp.raise_for_status()
            return resp.json()

    async def complete_json(
        self, *, system: str, user: str, schema_name: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        import json

        payload = {
            "model": self._chat_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": True},
            },
            "temperature": 0.2,
        }
        data = await self._post("/chat/completions", payload)
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)

    async def complete_text(
        self, *, system: str, user: str, max_tokens: int = 400, model: str | None = None
    ) -> str:
        payload = {
            "model": model or self._chat_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }
        data = await self._post("/chat/completions", payload)
        return (data["choices"][0]["message"]["content"] or "").strip()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # 配列入力で1リクエストにまとめる（バッチ化。M1 推奨A・§2.10 コスト最小化）。
        payload = {"model": self._embed_model, "input": texts}
        data = await self._post("/embeddings", payload)
        # API は index 昇順で返すが、念のため index でソートして順序を保証する。
        items = sorted(data["data"], key=lambda d: d["index"])
        return [item["embedding"] for item in items]


def build_llm_client() -> LLMClient | None:
    """settings に基づき実クライアントを生成する。キー未設定なら None（degrade）。"""
    if not settings.openai_api_key:
        return None
    return OpenAIClient(settings.openai_api_key)
