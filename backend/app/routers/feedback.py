"""フィードバックチャット API（NL-API-14 / 15）。

- GET  /api/feedback : 会話履歴の取得（本人スコープ・RLS）。
- POST /api/feedback : user 発話を保存 → GPT 応答 → assistant 発話を保存。

危機検知（M1 必須2・§7.4）:
  **FB チャットの user 発話も危機検知の入力源に含める**。ルールベース（＋将来 GPT）で陽性なら、
  assistant 応答内および画面フラグ（crisis_notice）で相談窓口をやさしく提示する。

ガードレール（§7.6）:
  システムプロンプト固定・ユーザー発話は「参考データ」ラベルで分離・出力後段フィルタを適用。

I/O 設計:
  外部 LLM 呼び出し中に DB 接続を占有しないよう、user 保存 → (tx 外で) LLM → assistant 保存の
  順にトランザクションを分ける。LLM 未設定時は定型のやさしい応答へ degrade する（§7.5）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..db import user_tx
from ..deps.auth import get_current_user
from ..deps.providers import get_llm_client
from ..schemas import FeedbackIn
from ..services.crisis import detect_crisis_in_texts, detect_crisis_llm
from ..services.guardrails import SYSTEM_PROMPT_FEEDBACK, sanitize_advice, wrap_user_data
from ..services.llm import LLMClient
from ..services.support_messages import crisis_support_text

router = APIRouter(prefix="/api", tags=["feedback"])

_CONTEXT_LIMIT = 10  # 応答生成に含める直近メッセージ数


@router.get("/feedback")
async def list_feedback(
    uid: str = Depends(get_current_user),
    prediction_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    """会話履歴を取得する（NL-API-14）。prediction_id 指定でその予測に紐づく会話に絞る。"""
    async with user_tx(uid) as conn:
        cur = await conn.execute(
            """
            select id, prediction_id, role, content, created_at
            from public.feedback_messages
            where user_id = %(uid)s
              and (%(pid)s::uuid is null or prediction_id = %(pid)s::uuid)
            order by created_at
            limit %(lim)s
            """,
            {"uid": uid, "pid": prediction_id, "lim": limit},
        )
        rows = await cur.fetchall()
    return {"messages": rows}


async def _generate_reply(
    client: LLMClient | None,
    history: list[dict],
    user_content: str,
    crisis: bool,
) -> str:
    """assistant 応答を生成する。LLM 未設定時は定型のやさしい応答へ degrade。"""
    support = crisis_support_text() if crisis else ""
    if client is None:
        base = "お気持ちを教えてくれてありがとうございます。記録を続けていきましょう。"
        return (base + ("\n\n" + support if support else "")).strip()

    ctx_lines = [f"{m['role']}: {m['content']}" for m in history[-_CONTEXT_LIMIT:]]
    prompt = (
        "これまでの会話（参考データ）:\n"
        + wrap_user_data("\n".join(ctx_lines), "会話履歴")
        + "\n"
        + wrap_user_data(user_content, "今回のフィードバック")
        + "\n共感的に、短く応答してください（医療的助言はしない）。"
    )
    if crisis:
        prompt += "\n※本人がつらい状態の可能性があります。責めず、やさしく寄り添う一言にしてください。"
    try:
        reply = await client.complete_text(
            system=SYSTEM_PROMPT_FEEDBACK, user=prompt, max_tokens=300
        )
    except Exception:  # noqa: BLE001 応答生成失敗は定型へフォールバック（会話を止めない）
        reply = "お話ししてくれてありがとうございます。無理のない範囲で続けていきましょう。"
    # 後段フィルタ（医療断定の混入を防ぐ）。
    reply, _ = sanitize_advice(reply or "")
    if crisis and support:
        reply = (reply + "\n\n" + support).strip()
    return reply


@router.post("/feedback", status_code=201)
async def post_feedback(
    body: FeedbackIn,
    uid: str = Depends(get_current_user),
    client: LLMClient | None = Depends(get_llm_client),
):
    """user 発話を保存 → 応答生成 → assistant 発話を保存（NL-API-15）。"""
    # 危機検知（user 発話を入力源に含める。M1 必須2・§7.4）。
    # OR 判定: ルールベース（キーワード）∨ GPT 文脈判定（§7.4-3・R1）。
    # LLM 未設定（client=None）や GPT 失敗時は detect_crisis_llm が False を返し、
    # ルールベースのみに degrade する（現挙動維持）。
    rule_crisis = detect_crisis_in_texts([body.content])
    gpt_crisis = await detect_crisis_llm(client, body.content)
    crisis = rule_crisis or gpt_crisis

    # 1) user 発話を保存し、応答生成用の直近履歴を取得（tx を短く保つ）。
    async with user_tx(uid) as conn:
        u_cur = await conn.execute(
            """
            insert into public.feedback_messages (user_id, prediction_id, role, content)
            values (%(uid)s, %(pid)s::uuid, 'user', %(c)s)
            returning id, prediction_id, role, content, created_at
            """,
            {"uid": uid, "pid": body.prediction_id, "c": body.content},
        )
        user_message = await u_cur.fetchone()
        h_cur = await conn.execute(
            """
            select role, content from public.feedback_messages
            where user_id = %(uid)s
              and (%(pid)s::uuid is null or prediction_id = %(pid)s::uuid)
            order by created_at desc limit %(lim)s
            """,
            {"uid": uid, "pid": body.prediction_id, "lim": _CONTEXT_LIMIT},
        )
        history = list(reversed(await h_cur.fetchall()))

    # 2) LLM 応答生成（DB 接続を占有しないよう tx 外で実行）。
    reply = await _generate_reply(client, history, body.content, crisis)

    # 3) assistant 発話を保存。
    async with user_tx(uid) as conn:
        a_cur = await conn.execute(
            """
            insert into public.feedback_messages (user_id, prediction_id, role, content)
            values (%(uid)s, %(pid)s::uuid, 'assistant', %(c)s)
            returning id, prediction_id, role, content, created_at
            """,
            {"uid": uid, "pid": body.prediction_id, "c": reply},
        )
        assistant_message = await a_cur.fetchone()

    return {
        "user_message": user_message,
        "assistant_message": assistant_message,
        "crisis_notice": crisis,
    }
