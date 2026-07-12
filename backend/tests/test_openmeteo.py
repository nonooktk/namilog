"""Open-Meteo 連携のテスト（§5.1）。

- derived の日長算出（春分で約12時間）。
- レスポンス → factor_values マッピング（気圧の前日比 delta・日照の秒→時間換算・寒暖差・湿度/天候）。
- fetch_daily_factors をフェイク getter で検証（ネットワーク不要）。
- 疎通テスト（1本）は実 Open-Meteo を叩く。鍵不要のため許容。ネットワーク不通なら skip。
"""
from __future__ import annotations

from datetime import date

import pytest

from _fakes import FakeMeteoGetter, _sample_meteo_payload
from app.services import openmeteo


def test_season_daylength_equinox_about_12h():
    # 春分（2026-03-20）は緯度によらず約12時間。
    dl = openmeteo.compute_season_daylength(date(2026, 3, 20), 35.68)
    assert 11.5 <= dl <= 12.5


def test_season_daylength_summer_longer_than_winter_north():
    summer = openmeteo.compute_season_daylength(date(2026, 6, 21), 35.68)
    winter = openmeteo.compute_season_daylength(date(2026, 12, 21), 35.68)
    assert summer > winter


def test_map_response_to_factor_values():
    mapped = openmeteo.map_response_to_factor_values(_sample_meteo_payload(), 35.68)
    d1 = mapped["2026-06-01"]
    d2 = mapped["2026-06-02"]
    # 気圧: 日次平均＋前日比 delta
    assert d1["barometric_pressure"]["v"] == 1012.0  # (1013+1011)/2
    assert d2["barometric_pressure"]["delta"] == pytest.approx(-1012.0 + 1004.0)  # 1004-1012
    # 日照: 秒→時間
    assert d1["sunshine_hours"]["v"] == 10.0
    assert d2["sunshine_hours"]["v"] == 5.0
    # 寒暖差
    assert d1["temperature_swing"]["v"] == 10.0
    # 湿度・天候コード
    assert d2["weather_humidity"]["v"] == 85.0  # (80+90)/2
    assert d2["weather_humidity"]["weather_code"] == 61
    # derived 日長
    assert d1["season_daylength"]["src"] == "derived"


def test_fetch_daily_factors_with_fake_getter():
    import asyncio

    getter = FakeMeteoGetter()
    mapped = asyncio.run(
        openmeteo.fetch_daily_factors(
            getter, 35.68, 139.76, "Asia/Tokyo", date(2026, 6, 1), date(2026, 6, 2)
        )
    )
    assert set(mapped) == {"2026-06-01", "2026-06-02"}
    # forecast パラメータが渡っている（archive でない）
    url, params = getter.calls[0]
    assert "forecast" in url
    assert params["timezone"] == "Asia/Tokyo"


def test_live_openmeteo_smoke():
    """実 Open-Meteo への疎通テスト（鍵不要・1本のみ）。ネットワーク不通なら skip。"""
    import asyncio

    import httpx

    getter = openmeteo.HttpxMeteoGetter()
    try:
        mapped = asyncio.run(
            openmeteo.fetch_daily_factors(
                getter, 35.68, 139.76, "Asia/Tokyo", date.today(), date.today()
            )
        )
    except (httpx.HTTPError, OSError) as exc:  # ネットワーク不通・DNS 等
        pytest.skip(f"Open-Meteo へ到達できないため skip: {exc}")
    # 当日分の日次指標が少なくとも1日ぶん取得できる。
    assert mapped, "Open-Meteo から日次指標を取得できませんでした"
    any_day = next(iter(mapped.values()))
    assert any(
        k in any_day
        for k in ("barometric_pressure", "sunshine_hours", "temperature_swing", "weather_humidity")
    )
