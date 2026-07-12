"""既定日付が JST（Asia/Tokyo）基準に統一されていることの回帰テスト（M4前半 QA Major-1）。

背景: 本番ホスティング（Render）はプロセス TZ が UTC で稼働する。素の `date.today()` は
JST 早朝（＝UTC 前日夜）に前日を返し、週次ノート冪等の基準日 `base` が前週へずれて版が
重複生成され得る（修正済みの TZ 境界バグの再発）。既定日付を `app_today()`（明示 ZoneInfo で
JST を算出＝プロセス TZ 非依存）へ統一した。

既存の TZ 境界テスト（test_prediction_loop.py）は `base` を明示指定するため、この「base 省略時の
既定解決」経路をカバーしていなかった。本テストがその経路を直接ガードする。DB 非依存・決定的。
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone


def test_app_today_is_jst_regardless_of_process_tz(monkeypatch):
    """app_today() は UTC 夜（JST 翌朝）でも JST の暦日を返す（プロセス TZ 非依存）。

    実時刻を JST 月曜 05:00（＝UTC 日曜 20:00）に固定し、UTC 側の暦日（日曜）ではなく
    JST 側の暦日（月曜）を返すことを検証する。`app_now` を差し替えて決定的にする。
    """
    from app import timeutils

    boundary_utc = datetime(2026, 7, 12, 20, 0, tzinfo=timezone.utc)  # JST 2026-07-13(月) 05:00
    monkeypatch.setattr(
        timeutils, "app_now", lambda: boundary_utc.astimezone(timeutils.APP_DEFAULT_TZ)
    )

    assert timeutils.app_today() == date(2026, 7, 13)          # JST 月曜
    assert timeutils.app_today() != boundary_utc.date()        # UTC 側の日曜（07-12）ではない


def test_refresh_weekly_note_default_base_uses_app_today(monkeypatch):
    """base 省略時、週次ノート冪等の基準日が app_today()（JST 今日）に解決される（Major-1 核心）。

    `_has_weekly_note_this_week` に渡る base を捕捉し、`date.today()`（プロセス TZ 依存）ではなく
    `app_today()` 由来であることを検証する。同一週ありを返して LLM 未到達で早期 return させるため、
    DB も実 LLM も不要（決定的）。もし既定が `date.today()` に戻ると、捕捉 base が実行日となり本検証は失敗する。
    """
    from app.services import notes as notes_module

    sentinel = date(2026, 7, 13)  # JST 月曜（app_today の固定値）
    monkeypatch.setattr(notes_module, "app_today", lambda: sentinel)

    captured: dict[str, date] = {}

    async def _fake_has_weekly(conn, uid, base):  # noqa: ANN001 - テスト用スタブ
        captured["base"] = base
        return True  # 同一週に版あり扱い → refresh は None で早期 return（LLM 未到達）

    monkeypatch.setattr(notes_module, "_has_weekly_note_this_week", _fake_has_weekly)

    class _TruthyClient:  # client is None 判定を通すためのダミー（呼ばれない）
        pass

    result = asyncio.run(
        notes_module.refresh_weekly_note(
            None, "user-1", _TruthyClient(), base=None, force=False
        )
    )

    assert result is None                    # 冪等スキップ経路
    assert captured["base"] == sentinel       # ★ 既定 base が app_today()（JST）に統一されている
