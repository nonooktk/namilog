"""外部指標 API（NL-API-03 / 04 / 08 / 11 / 12）。

- カタログ取得（12候補）
- 現在の選択取得（アクティブ3＋履歴）
- 選択の入れ替え（初期選定・入れ替え共通。§5.3「行は消さない」切替）
- 手入力の外部指標値の JSONB マージ
"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status

from ..db import user_tx
from ..deps.auth import get_current_user
from ..schemas import FactorSelectionIn, FactorValuesIn, ensure_not_future

router = APIRouter(prefix="/api", tags=["factors"])


@router.get("/factors/catalog")
async def get_catalog(uid: str = Depends(get_current_user)):
    """12 指標マスタを取得する（NL-API-03）。共有マスタ・read-only。"""
    async with user_tx(uid) as conn:
        cur = await conn.execute(
            """
            select factor_key, label, input_type, unit, description, sort_order
            from public.factor_catalog order by sort_order
            """
        )
        rows = await cur.fetchall()
    return {"catalog": rows}


@router.get("/factors/selection")
async def get_selection(uid: str = Depends(get_current_user)):
    """現在アクティブな3指標と、選択履歴を取得する（NL-API-11）。"""
    async with user_tx(uid) as conn:
        active_cur = await conn.execute(
            """
            select ef.factor_key, c.label, c.input_type, c.unit,
                   ef.activated_at
            from public.external_factors ef
            join public.factor_catalog c on c.factor_key = ef.factor_key
            where ef.user_id = %s and ef.is_active
            order by ef.activated_at
            """,
            (uid,),
        )
        active = await active_cur.fetchall()
        history_cur = await conn.execute(
            """
            select factor_key, is_active, activated_at, deactivated_at
            from public.external_factors
            where user_id = %s
            order by activated_at
            """,
            (uid,),
        )
        history = await history_cur.fetchall()
    return {"active": active, "history": history}


@router.put("/factors/selection")
async def put_selection(body: FactorSelectionIn, uid: str = Depends(get_current_user)):
    """3指標を選定／入れ替える（NL-API-04 / 12）。§5.3 の切替処理。

    - 外す指標: is_active=false, deactivated_at=now()（行は消さない）
    - 入れる指標: 既存の非アクティブ行があれば再アクティブ化、無ければ insert
    - factor_values の過去データは一切削除しない（P-3）
    - アクティブは常にちょうど3件（入力はスキーマで3件保証）
    """
    keys = body.factor_keys
    async with user_tx(uid) as conn:
        # 指定キーが factor_catalog に実在するか（FK でも守られるが、明快な 400 を返す）
        cur = await conn.execute(
            "select factor_key from public.factor_catalog where factor_key = any(%s)",
            (keys,),
        )
        found = {r["factor_key"] for r in await cur.fetchall()}
        missing = [k for k in keys if k not in found]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"未知の factor_key が含まれています: {missing}",
            )

        # 1) 新集合に含まれないアクティブ行を非アクティブ化（行は消さない）
        await conn.execute(
            """
            update public.external_factors
            set is_active = false, deactivated_at = now()
            where user_id = %s and is_active and not (factor_key = any(%s))
            """,
            (uid, keys),
        )
        # 2) 新集合の各キーをアクティブ化（既存の非アクティブ行を再利用、無ければ insert）
        for key in keys:
            upd = await conn.execute(
                """
                update public.external_factors
                set is_active = true, activated_at = now(), deactivated_at = null
                where user_id = %s and factor_key = %s and not is_active
                returning id
                """,
                (uid, key),
            )
            reactivated = await upd.fetchone()
            if reactivated is None:
                # 既にアクティブなら何もしない。どの行も無ければ新規 insert。
                exists = await conn.execute(
                    """
                    select 1 from public.external_factors
                    where user_id = %s and factor_key = %s and is_active
                    """,
                    (uid, key),
                )
                if await exists.fetchone() is None:
                    await conn.execute(
                        """
                        insert into public.external_factors (user_id, factor_key, is_active)
                        values (%s, %s, true)
                        """,
                        (uid, key),
                    )
    return await get_selection(uid)  # type: ignore[arg-type]


@router.put("/factor-values/{value_date}")
async def put_factor_values(
    value_date: date, body: FactorValuesIn, uid: str = Depends(get_current_user)
):
    """手入力の外部指標値を JSONB にマージ保存する（NL-API-08）。

    既存の values に対し `values || new` でキー単位マージ（同一日を複数回入力しても
    上書き・追記できる）。src='manual' を明示して保存する。
    """
    # value_date の未来日ガード（R1・§3.2「value_date は <= today」。データ汚染防止）
    try:
        ensure_not_future(value_date)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    # {"sleep": 6.5} → {"sleep": {"v": 6.5, "src": "manual"}} の形に整える
    shaped = {k: {"v": v, "src": "manual"} for k, v in body.values.items()}
    async with user_tx(uid) as conn:
        cur = await conn.execute(
            """
            insert into public.factor_values (user_id, value_date, values)
            values (%s, %s, %s::jsonb)
            on conflict (user_id, value_date)
            do update set values = public.factor_values.values || excluded.values,
                          updated_at = now()
            returning value_date, values, updated_at
            """,
            (uid, value_date, json.dumps(shaped)),
        )
        row = await cur.fetchone()
    return row
