"""期間ダイジェスト生成（ARCHITECTURE.md §4.6 / NL-API-19）。

詳細履歴画面から、ユーザー指定期間（from〜to）の体調を GPT-4o-mini が「振り返り」として
要約する。生成物は §2.12 `digests` に保存し、同一期間の再リクエストは保存済み content を返す
（再生成しない・§4.5）。`force=true` のときだけ再生成し upsert する（呼び出しはルーター側）。

入力（期間内で集約。§4.6）:
  1. 実測: 期間内の daily_records（actual_score ＋ comment）。
  2. 予測トレース: 同期間の predictions（advice ＋ 誤差 error/abs_error）。予測がどれくらい
     当たったかの材料。
  3. アクティブ3指標: external_factors(is_active) の3キーで factor_values.values から抽出した値。

コスト対策（§4.5 / §4.6）:
  期間が長い場合でも代表値・要約でトークンを圧縮してから GPT に渡す。全日のスコアはコンパクトな
  一覧に畳み、コメント全文は「良かった日／悪かった日の候補（スコア上位・下位）」に限定して渡す
  （good_days/bad_days の材料として十分で、入力を代表値に圧縮できる）。

ガードレール（§7.6 を適用。services/guardrails.py を再利用）:
  - システムプロンプトで医療断定・診断・服薬指示を禁止（SYSTEM_PROMPT_DIGEST）。
  - ユーザーコメントは wrap_user_data で「参考データ」ラベル分離（指示に従わせない）。
  - 後段フィルタ sanitize_digest_text で summary/note/coping を点検し、不適切表現は安全文言へ。
  - LLM 未設定（None）はルーター側で 503 degrade（§7.5 と同思想。本サービスは client 前提）。

危機検知との関係（§4.6）:
  危機検知の入力源3経路（§7.4）は変更しない。ダイジェスト出力には後段フィルタの安全文言
  フォールバックのみを適用し、ダイジェストを新たな危機検知の入力源には加えない。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .guardrails import (
    SYSTEM_PROMPT_DIGEST,
    sanitize_digest_text,
    wrap_user_data,
)
from .llm import LLMClient

# 生成モデル（§2.12 digests.model の既定と一致）。
DIGEST_MODEL = "gpt-4o-mini"

# コメント全文を渡す「良かった日／悪かった日」の候補件数（スコア上位・下位それぞれ）。
# good_days/bad_days は各最大3件（§4.6 の maxItems=3）なので、材料は少し多めの各5件に絞る。
CANDIDATE_DAYS = 5
# 1コメントあたりの最大文字数（トークン圧縮。長文コメントは頭を切り出す）。
COMMENT_CLIP = 140

# §4.6 の構造化出力スキーマ（strict）。スマホ1画面に収まる分量を maxLength/maxItems で担保。
DIGEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string", "maxLength": 300},
        "good_days": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "date": {"type": "string"},
                    "note": {"type": "string", "maxLength": 120},
                    "coping": {"type": "string", "maxLength": 120},
                },
                "required": ["date", "note", "coping"],
            },
        },
        "bad_days": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "date": {"type": "string"},
                    "note": {"type": "string", "maxLength": 120},
                    "coping": {"type": "string", "maxLength": 120},
                },
                "required": ["date", "note", "coping"],
            },
        },
    },
    "required": ["summary", "good_days", "bad_days"],
}


@dataclass
class PeriodData:
    """期間内から集めた集約データ（LLM 入力の素）。DB 接続を離した後で使えるよう値のみ保持。"""

    records: list[dict[str, Any]] = field(default_factory=list)  # {record_date, actual_score, comment}
    predictions: list[dict[str, Any]] = field(default_factory=list)  # {target_date, advice, error, abs_error}
    active_keys: list[str] = field(default_factory=list)
    factor_rows: list[dict[str, Any]] = field(default_factory=list)  # {value_date, values}

    @property
    def record_count(self) -> int:
        return len(self.records)


async def collect_period_data(
    conn, uid: str, period_from: date, period_to: date
) -> PeriodData:
    """期間内の実測・予測・アクティブ3指標値を収集する（§4.6 の入力3種）。

    conn はユーザー文脈トランザクション（user_tx）を想定。RLS で本人の行のみ取得できる。
    外部 LLM 呼び出しは行わない（DB 接続を長く占有しないため、生成は tx の外で行う）。
    """
    rec_cur = await conn.execute(
        """
        select record_date, actual_score, comment
        from public.daily_records
        where user_id = %(uid)s
          and record_date >= %(from)s
          and record_date <= %(to)s
        order by record_date asc
        """,
        {"uid": uid, "from": period_from, "to": period_to},
    )
    records = await rec_cur.fetchall()

    pred_cur = await conn.execute(
        """
        select target_date, advice, error, abs_error
        from public.predictions
        where user_id = %(uid)s
          and target_date >= %(from)s
          and target_date <= %(to)s
        order by target_date asc
        """,
        {"uid": uid, "from": period_from, "to": period_to},
    )
    predictions = await pred_cur.fetchall()

    keys_cur = await conn.execute(
        "select factor_key from public.external_factors where user_id = %s and is_active",
        (uid,),
    )
    active_keys = [r["factor_key"] for r in await keys_cur.fetchall()]

    factor_rows: list[dict[str, Any]] = []
    if active_keys:
        fv_cur = await conn.execute(
            """
            select value_date, values
            from public.factor_values
            where user_id = %(uid)s
              and value_date >= %(from)s
              and value_date <= %(to)s
            order by value_date asc
            """,
            {"uid": uid, "from": period_from, "to": period_to},
        )
        factor_rows = await fv_cur.fetchall()

    return PeriodData(
        records=records,
        predictions=predictions,
        active_keys=active_keys,
        factor_rows=factor_rows,
    )


def _clip(text: str | None, n: int = COMMENT_CLIP) -> str:
    t = (text or "").strip()
    return t if len(t) <= n else t[:n] + "…"


def _factor_value_scalar(raw: Any) -> Any:
    """factor_values.values の値を人間可読なスカラーへ。{"v":..,"unit":..} 形式は v を採る。"""
    if isinstance(raw, dict):
        return raw.get("v", raw)
    return raw


def _factors_for_date(data: PeriodData, d: date) -> str:
    """指定日のアクティブ指標値を "key=値" の短い文字列にする（無ければ空）。"""
    if not data.active_keys:
        return ""
    iso = d.isoformat()
    values: dict[str, Any] = {}
    for row in data.factor_rows:
        if row["value_date"].isoformat() == iso:
            values = row["values"] or {}
            break
    parts: list[str] = []
    for key in data.active_keys:
        if key in values and values[key] is not None:
            parts.append(f"{key}={_factor_value_scalar(values[key])}")
    return ", ".join(parts)


def build_user_prompt(data: PeriodData, *, period_from: date, period_to: date) -> str:
    """収集データから LLM 用のユーザープロンプトを組み立てる（トークン圧縮込み。§4.6）。"""
    lines: list[str] = []
    lines.append(
        f"対象期間: {period_from.isoformat()} 〜 {period_to.isoformat()}"
        f"（実測 {data.record_count} 日分）。1=最不調〜10=最好調。"
    )

    # 全日のスコアはコンパクトな一覧に畳む（トークン圧縮）。
    scores = ", ".join(
        f"{r['record_date'].isoformat()}={r['actual_score']}" for r in data.records
    )
    lines.append("期間内の実測スコア（日付昇順）: " + (scores or "記録なし"))

    # 予測の当たり具合（誤差の代表値＋一言対策の例）。突合済みのみ集計。
    scored = [p for p in data.predictions if p.get("abs_error") is not None]
    if scored:
        mae = sum(int(p["abs_error"]) for p in scored) / len(scored)
        lines.append(
            f"予測の当たり具合: 突合 {len(scored)} 日、平均絶対誤差(MAE) 約 {mae:.1f} 点。"
        )
    advices = [p["advice"] for p in data.predictions if p.get("advice")]
    if advices:
        lines.append("予測時の一言対策の例: " + " / ".join(_clip(a, 40) for a in advices[:3]))

    # 良かった日／悪かった日の候補（スコア上位・下位）だけコメント全文を渡す（圧縮の要）。
    with_score = [r for r in data.records if r.get("actual_score") is not None]
    good = sorted(with_score, key=lambda r: r["actual_score"], reverse=True)[:CANDIDATE_DAYS]
    bad = sorted(with_score, key=lambda r: r["actual_score"])[:CANDIDATE_DAYS]

    def _day_block(title: str, rows: list[dict[str, Any]]) -> str:
        parts: list[str] = [title]
        for r in rows:
            d = r["record_date"]
            factors = _factors_for_date(data, d)
            factor_suffix = f" / 指標: {factors}" if factors else ""
            parts.append(
                f"- {d.isoformat()}: スコア{r['actual_score']}"
                f" / コメント: {_clip(r['comment']) or '(なし)'}{factor_suffix}"
            )
        return "\n".join(parts)

    if good:
        lines.append(
            wrap_user_data(
                _day_block("スコアが高かった日の候補:", good),
                "調子が良かった日の候補",
            )
        )
    if bad:
        lines.append(
            wrap_user_data(
                _day_block("スコアが低かった日の候補:", bad),
                "調子が悪かった日の候補",
            )
        )

    lines.append(
        "上記を根拠に、期間全体のダイジェスト（summary）と、調子の良かった日（good_days）／"
        "悪かった日（bad_days）それぞれ最大3件を、指定 JSON スキーマで返してください。"
        "各 date は上の候補に現れた実在の日付のみを使ってください。"
    )
    return "\n".join(lines)


def _sanitize_day_items(items: Any, valid_dates: set[str]) -> list[dict[str, str]]:
    """good_days/bad_days を後段フィルタ（§7.6）に通し、幻覚日付を除外する（§4.6・レビュー#4）。

    LLM が返す date は、期間内かつ実測が存在する日付集合（valid_dates）に含まれるものだけ採用する。
    期間外・実在しない日付（ハルシネーション）の項目は捨てる（存在しない日を「良かった日」と
    示さない）。最大3件（§4.6 の maxItems=3）。
    """
    out: list[dict[str, str]] = []
    if not isinstance(items, list):
        return out
    for it in items:
        if len(out) >= 3:
            break
        if not isinstance(it, dict):
            continue
        d = str(it.get("date", ""))
        if d not in valid_dates:
            # 期間外・幻覚日付は除外する（実測のある日付のみ許可）。
            continue
        note, _ = sanitize_digest_text(str(it.get("note", "")))
        coping, _ = sanitize_digest_text(str(it.get("coping", "")))
        out.append({"date": d, "note": note, "coping": coping})
    return out


async def generate_digest_content(
    client: LLMClient, data: PeriodData, *, period_from: date, period_to: date
) -> dict[str, Any]:
    """LLM でダイジェスト content（{summary, good_days, bad_days}）を生成する（§4.6）。

    DB 接続を占有しないよう、事前収集した PeriodData のみを使う（tx の外で呼ぶ想定）。
    出力は後段フィルタ（§7.6）を通し、そのまま §2.12 digests.content に保存できる構造で返す。
    """
    user_prompt = build_user_prompt(data, period_from=period_from, period_to=period_to)
    result = await client.complete_json(
        system=SYSTEM_PROMPT_DIGEST,
        user=user_prompt,
        schema_name="namilog_digest",
        schema=DIGEST_SCHEMA,
    )

    # 実測が存在する日付集合（期間内）。LLM の date はこの集合内のみ採用する（幻覚日付除外・#4）。
    valid_dates = {r["record_date"].isoformat() for r in data.records}

    summary, _ = sanitize_digest_text(str(result.get("summary", "")))
    if not summary:
        summary = "この期間の記録をやさしく振り返った内容です（参考情報です）。"
    good_days = _sanitize_day_items(result.get("good_days"), valid_dates)
    bad_days = _sanitize_day_items(result.get("bad_days"), valid_dates)

    # digests.content の構造（§2.12 / §4.6 の json_schema）と一致させる。
    return {"summary": summary, "good_days": good_days, "bad_days": bad_days}
