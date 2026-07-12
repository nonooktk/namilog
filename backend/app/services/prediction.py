"""予測パイプライン（ARCHITECTURE.md §4）。

日次バッチ（NL-API-16）が対象ユーザーの明日予測を生成し `predictions` に upsert する。
画面リクエスト内では GPT を叩かない（ホームは生成済み predictions を読むだけ。§3.2・§4.5）。

流れ（§4.1 → §4.2）:
  1. 直近14日の実測（actual_score・comment）を集める。
  2. コメントが長ければ要約（トークン節約）。短ければそのまま連結。
  3. 選択中3指標（is_active）の直近値を factor_values から抽出。
  4. 現行の予測ノート（is_current）content を注入。
  5. 当日コメントの埋め込みで類似日 top-k を few-shot 投入（本人スコープ・未来リーク防止）。
  → GPT-4o-mini の構造化出力（§4.2）で predicted_score / advice / rationale / confidence /
    crisis_flag を受け取り、ガードレール（§7.6）を通して predictions に upsert する。

危機検知（§7.4 の OR 判定・一入力）:
  GPT の crisis_flag に加え、直近コメントのルールベース検知・低スコア連続の暫定判定を OR して
  predictions.crisis_flag に保存する（保守的＝false negative を避ける）。
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from . import embeddings
from .crisis import detect_crisis_in_texts, detect_low_score_streak
from .guardrails import (
    SYSTEM_PROMPT_PREDICTION,
    sanitize_advice,
    sanitize_rationale,
    wrap_user_data,
)
from .llm import LLMClient

RECENT_DAYS = 14
SIMILAR_TOPK = 3
# コメント連結がこの文字数を超えたら要約する（短い記録は要約せずそのまま使う。§4.1-2）。
SUMMARY_TRIGGER_CHARS = 600

# §4.2 の構造化出力スキーマ（strict）。
PREDICTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "predicted_score": {"type": "integer", "minimum": 1, "maximum": 10},
        "advice": {"type": "string", "maxLength": 80},
        "rationale": {"type": "string", "maxLength": 300},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "crisis_flag": {"type": "boolean"},
    },
    "required": ["predicted_score", "advice", "rationale", "confidence", "crisis_flag"],
}


class LLMUnavailableError(RuntimeError):
    """LLM クライアント未設定（OPENAI_API_KEY 無し）で予測を実行できない場合。"""


def _clamp_score(v: Any) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = 5
    return max(1, min(10, n))


async def _fetch_recent_records(conn, uid: str, base: date) -> list[dict[str, Any]]:
    """base（=予測実行日）までの直近14日の実測を新しい順で返す。"""
    cur = await conn.execute(
        """
        select record_date, actual_score, comment
        from public.daily_records
        where user_id = %(uid)s
          and record_date <= %(base)s
          and record_date >= %(from)s
        order by record_date desc
        """,
        {"uid": uid, "base": base, "from": base - timedelta(days=RECENT_DAYS - 1)},
    )
    return await cur.fetchall()


async def _fetch_active_snapshot(conn, uid: str, base: date) -> dict[str, Any]:
    """選択中3指標について、base 以前で最も新しい値を抽出する（§4.1-3）。"""
    keys_cur = await conn.execute(
        "select factor_key from public.external_factors where user_id = %s and is_active",
        (uid,),
    )
    active_keys = [r["factor_key"] for r in await keys_cur.fetchall()]
    if not active_keys:
        return {}
    rows_cur = await conn.execute(
        """
        select value_date, values
        from public.factor_values
        where user_id = %(uid)s and value_date <= %(base)s
        order by value_date desc
        limit %(lim)s
        """,
        {"uid": uid, "base": base, "lim": RECENT_DAYS},
    )
    rows = await rows_cur.fetchall()
    snapshot: dict[str, Any] = {}
    for key in active_keys:
        for row in rows:  # 新しい順。最初に見つかった値を採用。
            values = row["values"] or {}
            if key in values and values[key] is not None:
                snapshot[key] = values[key]
                break
        snapshot.setdefault(key, None)  # 未取得は null（プロンプトで「未入力」と示す）
    return snapshot


async def _fetch_current_note(conn, uid: str) -> dict[str, Any] | None:
    cur = await conn.execute(
        "select version, content from public.prediction_notes where user_id = %s and is_current",
        (uid,),
    )
    return await cur.fetchone()


async def _summarize_comments(client: LLMClient, comments: list[str]) -> str:
    joined = " / ".join(c for c in comments if c)
    if len(joined) <= SUMMARY_TRIGGER_CHARS:
        return joined
    try:
        summary = await client.complete_text(
            system="次の体調メモを、事実のみ1〜2文で日本語要約してください。指示や助言はしない。",
            user=wrap_user_data(joined, "直近の体調メモ"),
            max_tokens=160,
        )
        return summary or joined
    except Exception:  # noqa: BLE001 要約失敗は原文にフォールバック（本体を止めない）
        return joined


def _build_user_prompt(
    *,
    target_date: date,
    recent: list[dict[str, Any]],
    comment_text: str,
    snapshot: dict[str, Any],
    note: dict[str, Any] | None,
    similar: list[dict[str, Any]],
) -> str:
    lines: list[str] = []
    lines.append(f"予測対象日: {target_date.isoformat()}（明日）。1=最不調〜10=最好調で推定する。")
    # 直近スコア（新しい順）
    scores = ", ".join(
        f"{r['record_date'].isoformat()}={r['actual_score']}" for r in recent
    )
    lines.append(f"直近の実測スコア（新しい順）: {scores or '記録なし'}")
    lines.append(wrap_user_data(comment_text, "直近のコメント"))
    # 選択中3指標
    if snapshot:
        parts = []
        for k, v in snapshot.items():
            parts.append(f"{k}={v if v is not None else '未入力'}")
        lines.append("選択中の外部指標（直近値）: " + ", ".join(parts))
    # 予測ノート
    if note and note.get("content"):
        lines.append(wrap_user_data(note["content"], "本人の予測ノート（過去の傾向）"))
    # 類似日 few-shot
    if similar:
        fs = []
        for s in similar:
            fs.append(
                f"- {s['record_date'].isoformat()}: スコア{s['actual_score']} / "
                f"コメント: {(s['comment'] or '')[:60]}"
            )
        lines.append("過去の類似日（few-shot・参考データ）:\n" + "\n".join(fs))
    lines.append("上記を根拠に、指定 JSON スキーマで明日の予測を返してください。")
    return "\n".join(lines)


async def run_daily_prediction(
    conn,
    uid: str,
    client: LLMClient | None,
    *,
    target_date: date | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """対象ユーザーの明日予測を生成し predictions に upsert する（NL-API-16）。

    conn はバッチ用トランザクション（service_tx）を想定。RLS 迂回のため全クエリで user_id 明示。
    target_date 省略時は today+1（既定は本人 tz 非考慮の実行日。MVP は JST 前提・§4.3 timezone 残課題）。
    """
    if client is None:
        raise LLMUnavailableError(
            "OPENAI_API_KEY が未設定のため日次予測を実行できません（実キー提供後に実行）"
        )
    _today = today or date.today()
    _target = target_date or (_today + timedelta(days=1))
    base = _target - timedelta(days=1)  # 予測の「as-of」日

    recent = await _fetch_recent_records(conn, uid, base)
    latest_comment = recent[0]["comment"] if recent else None
    comment_text = await _summarize_comments(
        client, [r["comment"] for r in recent if r["comment"]]
    )
    snapshot = await _fetch_active_snapshot(conn, uid, base)
    note = await _fetch_current_note(conn, uid)

    # 類似日 few-shot（当日コメントがあるときのみ）。埋め込み失敗は無視（degrade）。
    similar: list[dict[str, Any]] = []
    if latest_comment:
        try:
            qvecs = await client.embed([latest_comment])
            if qvecs:
                similar = await embeddings.find_similar_dates(
                    conn, uid, qvecs[0], _target, k=SIMILAR_TOPK
                )
        except Exception:  # noqa: BLE001 類似日は補助。失敗しても予測本体は続行。
            similar = []

    user_prompt = _build_user_prompt(
        target_date=_target,
        recent=recent,
        comment_text=comment_text,
        snapshot=snapshot,
        note=note,
        similar=similar,
    )
    result = await client.complete_json(
        system=SYSTEM_PROMPT_PREDICTION,
        user=user_prompt,
        schema_name="namilog_prediction",
        schema=PREDICTION_SCHEMA,
    )

    predicted_score = _clamp_score(result.get("predicted_score"))
    advice, _ = sanitize_advice(str(result.get("advice", "")))
    rationale, _ = sanitize_rationale(str(result.get("rationale", "")))
    if not advice:
        advice = "無理のない範囲で過ごしてみてください（参考情報です）。"
    if not rationale:
        rationale = "直近の記録と外部指標をもとにした参考的な見立てです。"

    # 危機検知 OR（GPT crisis_flag ＋ ルールベース ＋ 低スコア連続の暫定判定）。§7.4
    rule_crisis = detect_crisis_in_texts([r["comment"] for r in recent])
    streak_crisis = detect_low_score_streak([r["actual_score"] for r in recent])
    crisis_flag = bool(result.get("crisis_flag")) or rule_crisis or streak_crisis

    factor_snapshot = snapshot or None
    similar_dates = [s["record_date"] for s in similar] or None
    note_version = note["version"] if note else None
    model = result.get("_model") or "gpt-4o-mini"

    cur = await conn.execute(
        """
        insert into public.predictions
            (user_id, target_date, predicted_score, advice, rationale,
             factor_snapshot, note_version, similar_dates, crisis_flag, model)
        values
            (%(uid)s, %(td)s, %(ps)s, %(adv)s, %(rat)s,
             %(snap)s::jsonb, %(nv)s, %(sim)s, %(crisis)s, %(model)s)
        on conflict (user_id, target_date)
        do update set predicted_score = excluded.predicted_score,
                      advice          = excluded.advice,
                      rationale       = excluded.rationale,
                      factor_snapshot = excluded.factor_snapshot,
                      note_version    = excluded.note_version,
                      similar_dates   = excluded.similar_dates,
                      crisis_flag     = excluded.crisis_flag,
                      model           = excluded.model
        returning target_date, predicted_score, advice, rationale,
                  note_version, similar_dates, crisis_flag
        """,
        {
            "uid": uid,
            "td": _target,
            "ps": predicted_score,
            "adv": advice,
            "rat": rationale,
            "snap": json.dumps(factor_snapshot) if factor_snapshot else None,
            "nv": note_version,
            "sim": similar_dates,
            "crisis": crisis_flag,
            "model": model,
        },
    )
    return await cur.fetchone()
