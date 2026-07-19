"""期間ダイジェスト API（NL-API-19: POST /api/digest。§4.6）。

詳細履歴画面から、指定期間（from〜to）の体調を GPT が「振り返り」として要約する。

リクエストボディ（JSON）: `{ "from": "YYYY-MM-DD", "to": "YYYY-MM-DD", "force": false }`。
  ※ JSON のキーは予約語 `from` を使う。Pydantic 側は属性名 `from_` で受ける（schemas.DigestIn の
    before バリデータで写す）。この都合上、OpenAPI スキーマ上のプロパティ名は `from_` と表示される
    が、API が受け付ける実際のキーは `from` である（レビュー#7 の明記事項）。

流れ（§4.6 / §4.5 / §2.12・レビュー#1/#2 反映）:
  1. tx1（user_tx・RLS）: 保存済みダイジェスト（user_id, from, to 一致）を確認。
     - 保存済みがあり force でなければ、そのまま再利用して返す（再生成なし＝コスト対策 §4.5）。
       このパスは LLM 可用性に依存しない（LLM 未設定・障害時でもキャッシュは返せる。#1）。
     - 生成が必要なときのみ、続けて期間データ（実測・予測・アクティブ3指標）を収集する。
  2. 期間内の実測が 0 件なら 422（LLM を無駄に叩かない。§3.2）。
  3. 生成が必要になった時点で LLM 可用性を判定（未設定は 503 degrade。#1）。
  4. tx の外で LLM 生成（外部呼び出し中に DB 接続を占有しない。feedback.py と同方針）。
     通信エラー・タイムアウト・不正レスポンスは捕捉し、500 ではなく 503＋優しい文言へ degrade（#2/§7.5）。
  5. tx2（user_tx・RLS）: digests に upsert（同一期間は content/model/updated_at を更新）。

バリデーション（from<=to・to<=today・期間上限92日）は schemas.DigestIn（422）で担保する。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status

from ..db import user_tx
from ..deps.auth import get_current_user
from ..deps.providers import get_llm_client
from ..schemas import DigestIn
from ..services import digest as digest_service
from ..services.llm import LLMClient

router = APIRouter(prefix="/api", tags=["digest"])

# LLM 未設定・障害時の degrade 文言（§7.5・§4.6）。
_DEGRADE_DETAIL = "ダイジェストは今は作成できません。少し時間をおいて、また試してください。"


@router.post("/digest")
async def create_digest(
    body: DigestIn,
    uid: str = Depends(get_current_user),
    client: LLMClient | None = Depends(get_llm_client),
):
    """期間ダイジェストを生成/取得する（NL-API-19）。"""
    period_from = body.from_
    period_to = body.to

    # --- tx1: 既存確認（キャッシュ最優先。LLM 可用性に依存しない。#1）。必要なら期間データ収集 ---
    async with user_tx(uid) as conn:
        existing_cur = await conn.execute(
            """
            select content, model
            from public.digests
            where user_id = %(uid)s
              and period_from = %(from)s
              and period_to = %(to)s
            """,
            {"uid": uid, "from": period_from, "to": period_to},
        )
        existing = await existing_cur.fetchone()
        if existing is not None and not body.force:
            # 保存済みを再利用（再生成しない＝コスト対策 §4.5・§2.12）。LLM 未設定/障害でも返せる。
            return _response(
                existing["content"], existing["model"], period_from, period_to, cached=True
            )

        # ここに来るのは「保存済みなし」または「force」＝生成が必要なとき。期間データを収集する。
        data = await digest_service.collect_period_data(conn, uid, period_from, period_to)

    # 期間内に実測が無ければ、LLM を叩かず degrade（§3.2）。
    if data.record_count == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="この期間はまだ記録がありません。記録がたまってから試してみてね。",
        )

    # 生成が必要になった時点で LLM 可用性を判定（#1）。未設定は 503 degrade（§7.5・引き継ぎ）。
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY が未設定のため" + _DEGRADE_DETAIL,
        )

    # --- LLM 生成（tx の外。DB 接続を占有しない）。通信/タイムアウト/不正レスポンスは 503 へ（#2） ---
    try:
        content = await digest_service.generate_digest_content(
            client, data, period_from=period_from, period_to=period_to
        )
    except Exception:  # noqa: BLE001 外部 LLM 障害は degrade（500 を漏らさず 503 に変換。§7.5）
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_DEGRADE_DETAIL
        )
    model = digest_service.DIGEST_MODEL

    # --- tx2: upsert（同一期間は content/model/updated_at を更新） ---
    async with user_tx(uid) as conn:
        await conn.execute(
            """
            insert into public.digests (user_id, period_from, period_to, content, model)
            values (%(uid)s, %(from)s, %(to)s, %(content)s::jsonb, %(model)s)
            on conflict (user_id, period_from, period_to)
            do update set content    = excluded.content,
                          model      = excluded.model,
                          updated_at = now()
            """,
            {
                "uid": uid,
                "from": period_from,
                "to": period_to,
                "content": json.dumps(content),
                "model": model,
            },
        )

    return _response(content, model, period_from, period_to, cached=False)


def _response(content, model, period_from, period_to, *, cached: bool) -> dict:
    """レスポンス整形。content（{summary, good_days, bad_days}）を展開し、メタ情報を添える。"""
    return {
        "summary": content.get("summary", ""),
        "good_days": content.get("good_days", []),
        "bad_days": content.get("bad_days", []),
        "cached": cached,
        "model": model,
        "period_from": period_from.isoformat(),
        "period_to": period_to.isoformat(),
    }
