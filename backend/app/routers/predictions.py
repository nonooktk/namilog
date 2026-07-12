"""日次予測バッチ API（NL-API-16）。cron から内部トークンで呼ぶ内部エンドポイント。

流れ（対象ユーザーごと・§5.1 → §4）:
  1. Open-Meteo で当日＋対象日の外部指標を取得し factor_values にマージ（座標があれば）。
  2. 予測パイプライン（run_daily_prediction）で明日予測を生成し predictions に upsert。

バッチは service_tx（RLS 迂回）で実行し、全クエリで user_id を明示する（P-2）。外部障害は
ユーザー単位で握りつぶし、他ユーザーへ波及させない（§7.5）。
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status

from ..db import service_tx
from ..deps.batch import verify_batch_token
from ..deps.providers import get_llm_client, get_meteo_getter
from ..schemas import PredictionRunIn
from ..services import openmeteo, prediction
from ..services.llm import LLMClient
from ..services.openmeteo import MeteoGetter
from ..timeutils import app_today

router = APIRouter(prefix="/api", tags=["batch"])


async def _target_user_ids(conn, explicit: str | None) -> list[str]:
    if explicit:
        return [explicit]
    cur = await conn.execute("select id from public.profiles")
    return [str(r["id"]) for r in await cur.fetchall()]


@router.post("/predictions/run", dependencies=[Depends(verify_batch_token)])
async def run_predictions(
    body: PredictionRunIn,
    client: LLMClient | None = Depends(get_llm_client),
    meteo: MeteoGetter = Depends(get_meteo_getter),
):
    """対象ユーザーの明日予測を生成・upsert する（NL-API-16）。"""
    if client is None:
        # LLM 未設定では予測できない。実キー提供後に実行する旨を明示（§7.5・引き継ぎ）。
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY が未設定のため日次予測を実行できません（実キー提供後に実行）",
        )

    # 既定 today は JST の今日（app_today）。date.today() は Render(UTC) で前日にずれ、
    # target_date と Open-Meteo 取得日が実態と食い違う（M4前半 QA Major-1）。
    today = app_today()
    target = body.target_date or (today + timedelta(days=1))

    results: list[dict] = []
    errors: list[dict] = []
    async with service_tx() as conn:
        user_ids = await _target_user_ids(conn, body.user_id)

    for uid in user_ids:
        try:
            async with service_tx() as conn:
                # 1) Open-Meteo 取得＋マージ（座標があるときのみ）。失敗は握りつぶし予測は続行。
                prof_cur = await conn.execute(
                    "select latitude, longitude, timezone from public.profiles where id = %s",
                    (uid,),
                )
                prof = await prof_cur.fetchone()
                if prof and prof["latitude"] is not None and prof["longitude"] is not None:
                    try:
                        per_date = await openmeteo.fetch_daily_factors(
                            meteo,
                            float(prof["latitude"]),
                            float(prof["longitude"]),
                            prof["timezone"] or "Asia/Tokyo",
                            today,
                            target,
                        )
                        await openmeteo.merge_factor_values(conn, uid, per_date)
                    except Exception as exc:  # noqa: BLE001 外部障害は degrade
                        errors.append({"user_id": uid, "stage": "openmeteo", "error": str(exc)})

                # 2) 予測生成。
                row = await prediction.run_daily_prediction(
                    conn, uid, client, target_date=target, today=today
                )
                results.append({"user_id": uid, "prediction": row})
        except Exception as exc:  # noqa: BLE001 ユーザー単位で隔離
            errors.append({"user_id": uid, "stage": "predict", "error": str(exc)})

    return {"ran": len(results), "results": results, "errors": errors, "target_date": target.isoformat()}
