"""リクエスト／レスポンスのスキーマ（pydantic v2）。

バリデーション方針（ARCHITECTURE.md §3.2）:
  - actual_score / predicted_score は 1–10。
  - 日付は ISO-8601（date 型）。
  - factor_keys は factor_catalog に存在するキーのみ・ちょうど3件（存在チェックは DB 側 FK）。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, Field, field_validator


def _not_future(d: date) -> date:
    """record_date の未来日ガード（シナモロール M1 レビュー推奨）。

    タイムゾーン差を考慮し、UTC 基準の「明日」までを許容（端末側 tz で当日でも弾かない）。
    それより先の日付は入力ミスとみなして拒否する。
    """
    if d > date.today() + timedelta(days=1):
        raise ValueError("record_date に未来の日付は指定できません")
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
        return _not_future(v)


class RecordUpdateIn(BaseModel):
    actual_score: int = Field(ge=1, le=10)
    comment: str | None = None


class BulkRecordsIn(BaseModel):
    records: list[RecordIn] = Field(min_length=1)


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
