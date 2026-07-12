"""予測ノート API（NL-API-17 バッチ更新 / NL-API-18 現行取得）。

- POST /api/notes/refresh : 週次バッチ。内部トークンで保護。対象ユーザーごとに新版を作り current 切替。
- GET  /api/notes/current : 本人の現行ノート取得（RLS・ユーザー JWT）。
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status

from ..db import service_tx, user_tx
from ..deps.auth import get_current_user
from ..deps.batch import verify_batch_token
from ..deps.providers import get_llm_client
from ..schemas import NotesRefreshIn
from ..services import notes as notes_service
from ..services.llm import LLMClient

router = APIRouter(prefix="/api", tags=["notes"])


@router.get("/notes/current")
async def get_current(uid: str = Depends(get_current_user)):
    """現行の予測ノートを取得する（NL-API-18）。未作成なら null。"""
    async with user_tx(uid) as conn:
        note = await notes_service.get_current_note(conn, uid)
    return {"note": note}


@router.post("/notes/refresh", dependencies=[Depends(verify_batch_token)])
async def refresh_notes(
    body: NotesRefreshIn,
    client: LLMClient | None = Depends(get_llm_client),
):
    """週次ノートを更新する（NL-API-17）。対象ユーザーごとに新版 insert＋current 切替。"""
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY が未設定のため週次ノート更新を実行できません（実キー提供後に実行）",
        )
    base = body.base or date.today()

    async with service_tx() as conn:
        if body.user_id:
            user_ids = [body.user_id]
        else:
            cur = await conn.execute("select id from public.profiles")
            user_ids = [str(r["id"]) for r in await cur.fetchall()]

    updated: list[dict] = []
    errors: list[dict] = []
    for uid in user_ids:
        try:
            async with service_tx() as conn:
                note = await notes_service.refresh_weekly_note(conn, uid, client, base=base)
                if note is not None:
                    updated.append({"user_id": uid, "note": note})
        except Exception as exc:  # noqa: BLE001 ユーザー単位で隔離
            errors.append({"user_id": uid, "error": str(exc)})

    return {"updated": len(updated), "results": updated, "errors": errors}
