"""ホーム API（NL-API-05）。本日の実測/予測＋明日の予測・対策＋危機案内フラグ。

予測は日次バッチ（M3・NL-API-16）が生成した predictions を読むだけ（画面内で GPT を叩かない）。
M2 では predictions が空なので degrade して「本日の予測はまだありません」を返す（§7.5）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..db import user_tx
from ..deps.auth import get_current_user

router = APIRouter(prefix="/api", tags=["home"])


@router.get("/home")
async def get_home(uid: str = Depends(get_current_user)):
    async with user_tx(uid) as conn:
        # 本人の timezone で「今日」を決める（既定 Asia/Tokyo）
        tz_cur = await conn.execute(
            "select coalesce(timezone, 'Asia/Tokyo') as tz from public.profiles where id = %s",
            (uid,),
        )
        tz_row = await tz_cur.fetchone()
        tz = tz_row["tz"] if tz_row else "Asia/Tokyo"

        # 本日の実測
        today_actual_cur = await conn.execute(
            """
            select actual_score, comment
            from public.daily_records
            where user_id = %s and record_date = (now() at time zone %s)::date
            """,
            (uid, tz),
        )
        today_actual = await today_actual_cur.fetchone()

        # 本日の予測（target_date = 今日。前日バッチが生成）
        today_pred_cur = await conn.execute(
            """
            select predicted_score, advice, rationale, crisis_flag
            from public.predictions
            where user_id = %s and target_date = (now() at time zone %s)::date
            """,
            (uid, tz),
        )
        today_pred = await today_pred_cur.fetchone()

        # 明日の予測（target_date = 今日+1）
        tomorrow_pred_cur = await conn.execute(
            """
            select target_date, predicted_score, advice, rationale, crisis_flag
            from public.predictions
            where user_id = %s and target_date = ((now() at time zone %s)::date + 1)
            """,
            (uid, tz),
        )
        tomorrow_pred = await tomorrow_pred_cur.fetchone()

    # degrade: 予測が未生成なら案内メッセージを添える（外部障害/未実装の局所化・§7.5）
    notice = None
    if tomorrow_pred is None and today_pred is None:
        notice = "本日の予測はまだありません"

    crisis_notice = bool(
        (today_pred and today_pred.get("crisis_flag"))
        or (tomorrow_pred and tomorrow_pred.get("crisis_flag"))
    )

    return {
        "today": {"actual": today_actual, "prediction": today_pred},
        "tomorrow": {"prediction": tomorrow_pred},
        "notice": notice,
        "crisis_notice": crisis_notice,
    }
