"""リクエスト／レスポンスのスキーマ（pydantic v2）。

バリデーション方針（ARCHITECTURE.md §3.2）:
  - actual_score / predicted_score は 1–10。
  - 日付は ISO-8601（date 型）。
  - factor_keys は factor_catalog に存在するキーのみ・ちょうど3件（存在チェックは DB 側 FK）。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from .timeutils import app_today

# バルク投入の件数上限（ARCHITECTURE.md §3.1「例:1回≤730件」＝約2年分。R2）。
BULK_MAX_RECORDS = 730

# 期間ダイジェストの期間上限（ARCHITECTURE.md §3.2 / §4.6「期間上限は92日」）。
# 期間は両端含む日数で数える（from と to が同日なら1日）。
DIGEST_MAX_DAYS = 92


def ensure_not_future(d: date) -> date:
    """日付の未来日ガード（ARCH §3.2「record_date / value_date は <= today」）。

    アプリ既定 tz（Asia/Tokyo）の「今日」より後の日付を拒否する。スキーマ内（record_date）と
    エンドポイントのパス引数（value_date）の両方から使う共通関数（R1）。基準日は
    `app_today()`（プロセス TZ 非依存の JST 今日）に統一する（M4前半 QA Major-1）。ValueError を送出する。
    """
    if d > app_today():
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


# ---- FB チャット（NL-API-15） ----
# 発話長の上限。過大入力によるトークン/コスト肥大とインジェクション面積の抑制（§7.6）。
FEEDBACK_MAX_CHARS = 2000
MI_MAX_CHARS = 2000


class FeedbackIn(BaseModel):
    # 紐づく予測（任意）。指定なしでも会話できる。
    prediction_id: str | None = None
    content: str = Field(min_length=1, max_length=FEEDBACK_MAX_CHARS)


# ---- MI セッション ----
class MiSessionStartIn(BaseModel):
    theme: str | None = Field(default=None, max_length=300)


class MiMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=MI_MAX_CHARS)


# ---- バッチ（NL-API-16 / 17。内部トークンで保護） ----
class PredictionRunIn(BaseModel):
    # 対象ユーザー（省略時は全ユーザー）。target_date 省略時は実行日+1（明日）。
    user_id: str | None = None
    target_date: date | None = None


class NotesRefreshIn(BaseModel):
    user_id: str | None = None
    # 週次ノートの集計基準日（省略時は実行日）。
    base: date | None = None
    # 冪等化の明示オーバーライド（既定 False）。同一 ISO 週に weekly_batch 版が既にあれば通常は
    # スキップするが、force=True で強制的に新版を作る（手動再生成・補正用）。P1（§7.5.1）。
    force: bool = False


# ---- 期間ダイジェスト（NL-API-19: POST /api/digest。§4.6） ----
class DigestIn(BaseModel):
    """期間ダイジェストの生成/取得リクエスト（§3.2・§4.6）。

    バリデーション（いずれも違反時は 422）:
      - `from <= to`（開始が終了より後は不可）。
      - `to <= today`（本人 timezone ＝ app_today() 基準の未来日を拒否。§3.2 未来日ガード）。
      - 期間上限は 92 日（両端含む日数。超過は拒否）。
    ※ 期間内の実測 0 件（422）は DB 参照が要るためルーター側で判定する。
    """

    # `from` は Python の予約語のため属性名は from_、JSON フィールド名は from。
    # Field(alias=...) は FastAPI の body モデル再処理時に pydantic の警告を誘発するため使わず、
    # mode="before" バリデータで JSON の "from" を "from_" に写して受ける。
    from_: date = Field(default=..., description="期間開始日（JSON キーは from）")
    to: date
    # 保存済みがあっても強制的に再生成して upsert する（既定 False＝保存済みを再利用）。
    force: bool = False

    @model_validator(mode="before")
    @classmethod
    def _map_reserved_from(cls, data: Any) -> Any:
        # JSON の予約語キー "from" を属性名 "from_" へ写す（alias を使わないための前処理）。
        if isinstance(data, dict) and "from" in data and "from_" not in data:
            data = {**data, "from_": data["from"]}
        return data

    @field_validator("to")
    @classmethod
    def _to_not_future(cls, v: date) -> date:
        # to の未来日ガード（from <= to のため from も自動的に未来日でなくなる）。
        return ensure_not_future(v)

    @model_validator(mode="after")
    def _check_range(self) -> "DigestIn":
        if self.from_ > self.to:
            raise ValueError("from は to 以前の日付を指定してください")
        # 両端含む日数。同日なら 1 日。
        span_days = (self.to - self.from_).days + 1
        if span_days > DIGEST_MAX_DAYS:
            raise ValueError(f"期間は最大 {DIGEST_MAX_DAYS} 日までです")
        return self
