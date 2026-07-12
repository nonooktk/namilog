"""予測ノートの週次更新（ARCHITECTURE.md §4.3）。

週1回、ユーザーごとに直近7日の予測誤差・コメント・FB・現行ノートから、本人固有の再現パターンを
簡潔な箇条書きに更新する。新版を insert し、旧版 is_current=false・新版 is_current=true に
**同一トランザクションで切り替える**（版管理・ロールバック可能）。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .guardrails import SYSTEM_PROMPT_NOTE, wrap_user_data
from .llm import LLMClient

NOTE_WINDOW_DAYS = 7


class LLMUnavailableError(RuntimeError):
    """LLM クライアント未設定でノート更新を実行できない場合。"""


async def get_current_note(conn, uid: str) -> dict[str, Any] | None:
    """現行（is_current）の予測ノートを取得する（NL-API-18）。"""
    cur = await conn.execute(
        """
        select version, content, source, created_at
        from public.prediction_notes
        where user_id = %s and is_current
        """,
        (uid,),
    )
    return await cur.fetchone()


async def _gather_inputs(conn, uid: str, base: date) -> dict[str, Any]:
    since = base - timedelta(days=NOTE_WINDOW_DAYS - 1)
    pred_cur = await conn.execute(
        """
        select target_date, predicted_score, actual_score, error
        from public.predictions
        where user_id = %(uid)s and target_date >= %(since)s and target_date <= %(base)s
        order by target_date
        """,
        {"uid": uid, "since": since, "base": base},
    )
    preds = await pred_cur.fetchall()

    rec_cur = await conn.execute(
        """
        select record_date, actual_score, comment
        from public.daily_records
        where user_id = %(uid)s and record_date >= %(since)s and record_date <= %(base)s
        order by record_date
        """,
        {"uid": uid, "since": since, "base": base},
    )
    records = await rec_cur.fetchall()

    fb_cur = await conn.execute(
        """
        select role, content
        from public.feedback_messages
        where user_id = %(uid)s and created_at >= %(since)s
        order by created_at
        """,
        {"uid": uid, "since": since},
    )
    feedback = await fb_cur.fetchall()

    current = await get_current_note(conn, uid)
    return {"preds": preds, "records": records, "feedback": feedback, "current": current}


def _build_note_prompt(inputs: dict[str, Any]) -> str:
    lines: list[str] = []
    preds = inputs["preds"]
    if preds:
        err_lines = ", ".join(
            f"{p['target_date'].isoformat()}: 予測{p['predicted_score']}/実測{p['actual_score']}/誤差{p['error']}"
            for p in preds
            if p["actual_score"] is not None
        )
        lines.append(f"直近の予測誤差: {err_lines or '突合済みデータなし'}")
    comments = " / ".join(r["comment"] for r in inputs["records"] if r["comment"])
    lines.append(wrap_user_data(comments, "直近のコメント"))
    fb = " / ".join(f"{m['role']}:{m['content']}" for m in inputs["feedback"])
    if fb:
        lines.append(wrap_user_data(fb, "直近のフィードバック"))
    current = inputs["current"]
    if current and current.get("content"):
        lines.append(wrap_user_data(current["content"], "現行の予測ノート"))
    lines.append(
        "本人固有の再現パターンを、誤差と FB を根拠に簡潔な箇条書きで更新してください。"
        "矛盾する古い記述は削除し、断定しすぎないでください。箇条書きのみを返します。"
    )
    return "\n".join(lines)


async def refresh_weekly_note(
    conn,
    uid: str,
    client: LLMClient | None,
    *,
    base: date | None = None,
) -> dict[str, Any] | None:
    """新版ノートを作成し current を切り替える（NL-API-17）。同一トランザクション。

    conn はバッチ用（service_tx）。RLS 迂回のため user_id を明示する（P-2）。
    更新すべき材料が無い場合は None を返す（無駄な版増加を避ける）。
    """
    if client is None:
        raise LLMUnavailableError(
            "OPENAI_API_KEY が未設定のため週次ノート更新を実行できません（実キー提供後に実行）"
        )
    _base = base or date.today()
    inputs = await _gather_inputs(conn, uid, _base)

    # 材料が全く無ければ更新しない（初回はオンボーディング等で別途 seed される想定）。
    if not inputs["preds"] and not inputs["records"] and not inputs["feedback"]:
        return None

    prompt = _build_note_prompt(inputs)
    content = await client.complete_text(
        system=SYSTEM_PROMPT_NOTE, user=prompt, max_tokens=500
    )
    content = (content or "").strip()
    if not content:
        return None

    # 次バージョン番号を採番（本人スコープ）。
    ver_cur = await conn.execute(
        "select coalesce(max(version), 0) as v from public.prediction_notes where user_id = %s",
        (uid,),
    )
    next_version = (await ver_cur.fetchone())["v"] + 1

    # current 切替（同一トランザクション。§4.3 の SQL）。
    await conn.execute(
        "update public.prediction_notes set is_current = false where user_id = %s and is_current",
        (uid,),
    )
    ins_cur = await conn.execute(
        """
        insert into public.prediction_notes (user_id, version, content, is_current, source)
        values (%(uid)s, %(v)s, %(c)s, true, 'weekly_batch')
        returning version, content, source, created_at
        """,
        {"uid": uid, "v": next_version, "c": content},
    )
    return await ins_cur.fetchone()
