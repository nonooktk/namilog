"""プロフィール API（NL-API-01）。オンボーディングの医療免責同意・プロフィール保存。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..db import user_tx
from ..deps.auth import get_current_user
from ..schemas import ProfileIn

router = APIRouter(prefix="/api", tags=["profile"])


@router.get("/profile")
async def get_profile(uid: str = Depends(get_current_user)):
    """本人のプロフィールを取得する。profiles 行は登録時トリガーで自動生成済み。"""
    async with user_tx(uid) as conn:
        cur = await conn.execute(
            """
            select id, display_name, latitude, longitude, timezone,
                   medical_disclaimer_agreed_at, onboarded_at, created_at, updated_at
            from public.profiles where id = %s
            """,
            (uid,),
        )
        row = await cur.fetchone()
    return row


@router.put("/profile")
async def update_profile(body: ProfileIn, uid: str = Depends(get_current_user)):
    """プロフィールを更新（NL-API-01）。医療免責に同意したら同意時刻とオンボーディング完了を記録。"""
    async with user_tx(uid) as conn:
        # COALESCE で「渡された項目だけ更新」。timezone は null なら既存値を維持。
        cur = await conn.execute(
            """
            update public.profiles
            set display_name = coalesce(%(display_name)s, display_name),
                latitude     = coalesce(%(latitude)s, latitude),
                longitude    = coalesce(%(longitude)s, longitude),
                timezone     = coalesce(%(timezone)s, timezone),
                medical_disclaimer_agreed_at =
                    case when %(agree)s then coalesce(medical_disclaimer_agreed_at, now())
                         else medical_disclaimer_agreed_at end,
                onboarded_at =
                    case when %(agree)s then coalesce(onboarded_at, now())
                         else onboarded_at end
            where id = %(uid)s
            returning id, display_name, latitude, longitude, timezone,
                      medical_disclaimer_agreed_at, onboarded_at, updated_at
            """,
            {
                "display_name": body.display_name,
                "latitude": body.latitude,
                "longitude": body.longitude,
                "timezone": body.timezone,
                "agree": body.agree_medical_disclaimer,
                "uid": uid,
            },
        )
        row = await cur.fetchone()
    return row
