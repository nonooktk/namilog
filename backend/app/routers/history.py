"""履歴時系列 API（NL-API-10）。波グラフ用の [{date, actual, predicted}] を返す。"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from ..db import user_tx
from ..deps.auth import get_current_user

router = APIRouter(prefix="/api", tags=["history"])


@router.get("/history/series")
async def get_series(
    uid: str = Depends(get_current_user),
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
):
    """波グラフ用の時系列。実測と予測を日付で結合し、日付昇順で返す。"""
    async with user_tx(uid) as conn:
        cur = await conn.execute(
            """
            select coalesce(dr.record_date, p.target_date) as date,
                   dr.actual_score  as actual,
                   p.predicted_score as predicted
            from public.daily_records dr
            full outer join public.predictions p
              on p.user_id = dr.user_id and p.target_date = dr.record_date
            where coalesce(dr.user_id, p.user_id) = %(uid)s
              and (%(from)s::date is null or coalesce(dr.record_date, p.target_date) >= %(from)s::date)
              and (%(to)s::date   is null or coalesce(dr.record_date, p.target_date) <= %(to)s::date)
            order by date asc
            """,
            {"uid": uid, "from": from_, "to": to},
        )
        rows = await cur.fetchall()
    return {"series": rows}
