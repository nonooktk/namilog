"""アプリ共通の日付・タイムゾーンユーティリティ。

本番ホスティング（Render 等）はプロセス TZ が UTC で稼働するため、素の `date.today()` /
naive `datetime.now()` は「日本の今日」とずれる（JST 早朝＝UTC 前日夜に前日を返す）。
日付の既定値・境界判定は必ずアプリ既定 tz（Asia/Tokyo）基準に統一する。

方針の根拠:
  - home.py は SQL 側 `(now() at time zone tz)::date` で「今日」を算出しており、プロセス TZ 非依存。
    Python 側の日付判定も同じ JST 基準に揃える（ARCHITECTURE.md §4.3）。
  - M4前半 QA Major-1: 週次ノート冪等の基準日・予測 target_date の既定などで `date.today()` を
    使うと Render(UTC) で週境界がずれ、修正済みの重複バグが再発する。ここに集約して排除する。

`datetime.now(ZoneInfo(...))` は明示 tz を渡すためプロセス TZ（環境変数 `TZ` / OS 設定）に
一切依存しない。これが JST 基準を保証する要点。
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

# アプリ既定タイムゾーン。単一の真実の源（SQL 用の文字列表現と Python 用の ZoneInfo）。
APP_DEFAULT_TZ_NAME = "Asia/Tokyo"
APP_DEFAULT_TZ = ZoneInfo(APP_DEFAULT_TZ_NAME)


def app_now() -> datetime:
    """アプリ既定 tz（Asia/Tokyo）の現在時刻（aware）。プロセス TZ 非依存。"""
    return datetime.now(APP_DEFAULT_TZ)


def app_today() -> date:
    """アプリ既定 tz（Asia/Tokyo）の「今日」。プロセス TZ 非依存。

    本番プロセスが UTC でも日本の暦日を返す。日付の既定値・週境界判定に使う
    （`date.today()` は使わない）。テストは `app_now` を差し替えて境界を固定できる。
    """
    return app_now().date()
