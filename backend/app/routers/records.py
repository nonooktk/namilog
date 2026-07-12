"""体調記録 API（NL-API-02 / 06 / 07 / 09）。

- 過去ログ一括入力（オンボーディング）
- 実測スコア＋コメント登録／修正（予測突合を同一トランザクションで実行。§4.4）
- 履歴一覧（実測・予測を結合）
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import AsyncConnection

from ..db import user_tx
from ..deps.auth import get_current_user
from ..schemas import BulkRecordsIn, RecordIn, RecordUpdateIn
from ..services.crisis import detect_crisis_rule_based

router = APIRouter(prefix="/api", tags=["records"])


async def _match_prediction(
    conn: AsyncConnection, uid: str, record_date: date, actual_score: int
) -> dict | None:
    """予測突合（P-4 / §4.4）。同一 user_id かつ target_date=record_date の予測に誤差を書く。

    predictions が空でも 0 行更新で正常終了する（silent failure を作らない明示ステップ）。
    """
    cur = await conn.execute(
        """
        update public.predictions
        set actual_score = %(actual)s,
            error        = %(actual)s - predicted_score,
            abs_error    = abs(%(actual)s - predicted_score),
            scored_at    = now()
        where user_id = %(uid)s and target_date = %(d)s
        returning predicted_score, actual_score, error, abs_error
        """,
        {"actual": actual_score, "uid": uid, "d": record_date},
    )
    return await cur.fetchone()


@router.post("/records/bulk", status_code=status.HTTP_201_CREATED)
async def bulk_records(body: BulkRecordsIn, uid: str = Depends(get_current_user)):
    """過去ログ一括入力（NL-API-02）。同一日は upsert（上書き）。"""
    inserted = 0
    async with user_tx(uid) as conn:
        for rec in body.records:
            await conn.execute(
                """
                insert into public.daily_records (user_id, record_date, actual_score, comment)
                values (%s, %s, %s, %s)
                on conflict (user_id, record_date)
                do update set actual_score = excluded.actual_score,
                              comment = excluded.comment,
                              updated_at = now()
                """,
                (uid, rec.record_date, rec.actual_score, rec.comment),
            )
            inserted += 1
    return {"saved": inserted}


@router.post("/records", status_code=status.HTTP_201_CREATED)
async def create_record(body: RecordIn, uid: str = Depends(get_current_user)):
    """実測スコア＋コメント登録（NL-API-06）。予測突合・危機検知を同時に行う。"""
    crisis = detect_crisis_rule_based(body.comment)
    async with user_tx(uid) as conn:
        cur = await conn.execute(
            """
            insert into public.daily_records (user_id, record_date, actual_score, comment)
            values (%s, %s, %s, %s)
            on conflict (user_id, record_date)
            do update set actual_score = excluded.actual_score,
                          comment = excluded.comment,
                          updated_at = now()
            returning id, record_date, actual_score, comment, updated_at
            """,
            (uid, body.record_date, body.actual_score, body.comment),
        )
        row = await cur.fetchone()
        matched = await _match_prediction(conn, uid, body.record_date, body.actual_score)
    # 埋め込み生成（§2.10）は M3。ここでは呼び出さない。
    return {"record": row, "matched_prediction": matched, "crisis_notice": crisis}


@router.put("/records/{record_date}")
async def update_record(
    record_date: date, body: RecordUpdateIn, uid: str = Depends(get_current_user)
):
    """実測の修正（NL-API-07）。突合もやり直す。"""
    crisis = detect_crisis_rule_based(body.comment)
    async with user_tx(uid) as conn:
        cur = await conn.execute(
            """
            update public.daily_records
            set actual_score = %s, comment = %s, updated_at = now()
            where user_id = %s and record_date = %s
            returning id, record_date, actual_score, comment, updated_at
            """,
            (body.actual_score, body.comment, uid, record_date),
        )
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="指定日の記録が見つかりません",
            )
        matched = await _match_prediction(conn, uid, record_date, body.actual_score)
    return {"record": row, "matched_prediction": matched, "crisis_notice": crisis}


@router.get("/records")
async def list_records(
    uid: str = Depends(get_current_user),
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
):
    """履歴一覧（NL-API-09）。実測と予測を日付で結合して返す。"""
    async with user_tx(uid) as conn:
        cur = await conn.execute(
            """
            select coalesce(dr.record_date, p.target_date) as date,
                   dr.actual_score,
                   dr.comment,
                   p.predicted_score,
                   p.advice,
                   p.error,
                   p.abs_error
            from public.daily_records dr
            full outer join public.predictions p
              on p.user_id = dr.user_id and p.target_date = dr.record_date
            where coalesce(dr.user_id, p.user_id) = %(uid)s
              and (%(from)s::date is null or coalesce(dr.record_date, p.target_date) >= %(from)s::date)
              and (%(to)s::date   is null or coalesce(dr.record_date, p.target_date) <= %(to)s::date)
            order by date desc
            """,
            {"uid": uid, "from": from_, "to": to},
        )
        rows = await cur.fetchall()
    return {"records": rows}
