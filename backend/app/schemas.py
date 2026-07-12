"""リクエスト／レスポンスのスキーマ（pydantic v2）。

バリデーション方針（ARCHITECTURE.md §3.2）:
  - actual_score / predicted_score は 1–10。
  - 日付は ISO-8601（date 型）。
  - factor_keys は factor_catalog に存在するキーのみ・ちょうど3件（存在チェックは DB 側 FK）。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator

# バルク投入の件数上限（ARCHITECTURE.md §3.1「例:1回≤730件」＝約2年分。R2）。
BULK_MAX_RECORDS = 730

# 未来日ガードの基準タイムゾーン。MVP はアプリ既定（Asia/Tokyo）を基準にする。
# 本人 timezone に基づく厳密判定は M3 の timezone 残課題（ARCH §9）で精緻化する（P2）。
APP_DEFAULT_TZ = ZoneInfo("Asia/Tokyo")


def _app_today() -> date:
    return datetime.now(APP_DEFAULT_TZ).date()


def ensure_not_future(d: date) -> date:
    """日付の未来日ガード（ARCH §3.2「record_date / value_date は <= today」）。

    アプリ既定 tz（Asia/Tokyo）の「今日」より後の日付を拒否する。スキーマ内（record_date）と
    エンドポイントのパス引数（value_date）の両方から使う共通関数（R1）。ValueError を送出する。
    """
    if d > _app_today():
        raise ValueError("未来の日付は指定できません")
    return d


# ---- プロフィール（NL-API-01） ----
class ProfileIn(BaseModel):
    display_name: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    timezone: str | None = None
    # 医療免責への同意。true でオンボーディング完了時刻を記録する。
    agree_medical_disclaimer: bool = False


# ---- 体調記録（NL-API-02 / 06 / 07） ----
class RecordIn(BaseModel):
    record_date: date
    actual_score: int = Field(ge=1, le=10)
    comment: str | None = None

    @field_validator("record_date")
    @classmethod
    def _no_future(cls, v: date) -> date:
        return ensure_not_future(v)


class RecordUpdateIn(BaseModel):
    actual_score: int = Field(ge=1, le=10)
    comment: str | None = None


class BulkRecordsIn(BaseModel):
    # 件数上限で過大投入によるメモリ/トランザクション肥大を防ぐ（R2・§3.1）。
    records: list[RecordIn] = Field(min_length=1, max_length=BULK_MAX_RECORDS)


# ---- 指標選定（NL-API-04 / 12） ----
class FactorSelectionIn(BaseModel):
    factor_keys: list[str]

    @field_validator("factor_keys")
    @classmethod
    def _exactly_three_unique(cls, v: list[str]) -> list[str]:
        if len(v) != 3:
            raise ValueError("factor_keys はちょうど3件で指定してください")
        if len(set(v)) != 3:
            raise ValueError("factor_keys に重複があります")
        return v


# ---- 手入力の外部指標値（NL-API-08） ----
class FactorValuesIn(BaseModel):
    # 例: {"sleep": 6.5, "medication": "ok"} を factor_values.values にマージ
    values: dict[str, Any] = Field(min_length=1)
