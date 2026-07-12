"""Open-Meteo 外部指標取得（ARCHITECTURE.md §5.1）。

鍵不要・無料。`profiles.latitude/longitude`（粗い座標）で気圧・日照・寒暖差・天候/湿度を取得し、
`factor_values.values` に日次マージする。derived の `season_daylength` は API 不要で算出する。

- forecast: `https://api.open-meteo.com/v1/forecast`（当日＋数日先。日次予測の直前）
- archive : `https://archive-api.open-meteo.com/v1/archive`（過去補完・欠測穴埋め。§5.1）

テスト方針:
  HTTP アクセスは注入可能な `MeteoGetter` 越しに行い、通常テストはフェイクで検証する。
  Open-Meteo は鍵不要のため、疎通テスト1本のみ実 API を叩いてもよい（それ以外はモック）。

factor_key マッピング（§5.1）:
  barometric_pressure ← surface_pressure(hourly) の日次代表値＋前日比の差分
  sunshine_hours      ← sunshine_duration(daily, 秒) → 時間換算
  temperature_swing   ← temperature_2m_max − temperature_2m_min(daily)
  weather_humidity    ← weather_code(daily) ＋ relative_humidity_2m(hourly) の代表値
  season_daylength    ← 日付＋緯度から算出（derived・API 不要）
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any, Protocol

import httpx

from ..config import settings

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

_DAILY_VARS = "sunshine_duration,temperature_2m_max,temperature_2m_min,weather_code"
_HOURLY_VARS = "surface_pressure,relative_humidity_2m"


class MeteoGetter(Protocol):
    """Open-Meteo への GET を抽象化する（テストでフェイクに差し替え可能にするため）。"""

    async def get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        ...


class HttpxMeteoGetter:
    """httpx による実 GET 実装。"""

    def __init__(
        self,
        *,
        timeout: float | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._timeout = timeout if timeout is not None else settings.external_http_timeout
        self._external_client = http_client

    async def get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._external_client is not None:
            resp = await self._external_client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()


# ---------------------------------------------------------------------------
# derived: 日長（季節位相）— API 不要
# ---------------------------------------------------------------------------
def compute_season_daylength(d: date, latitude: float) -> float:
    """日付＋緯度から日長（昼間の時間・hours）を算出する（§5.1 season_daylength）。

    標準的な日の出方程式による近似。極夜/白夜は 0〜24 にクランプする。
    """
    n = d.timetuple().tm_yday
    # 太陽赤緯（近似, degrees）
    decl = -23.44 * math.cos(math.radians((360.0 / 365.0) * (n + 10)))
    lat_r = math.radians(latitude)
    decl_r = math.radians(decl)
    cos_h = -math.tan(lat_r) * math.tan(decl_r)
    # 極夜/白夜のクランプ
    if cos_h <= -1:
        return 24.0
    if cos_h >= 1:
        return 0.0
    h = math.degrees(math.acos(cos_h))  # 時角（度）
    return round(2 * h / 15.0, 2)       # 15度/時 → 時間、片側×2


# ---------------------------------------------------------------------------
# 取得＋マッピング
# ---------------------------------------------------------------------------
def _mean(values: list[float | None]) -> float | None:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


def _group_hourly_by_date(hourly: dict[str, Any], key: str) -> dict[str, list[float | None]]:
    """hourly 配列を日付（YYYY-MM-DD）ごとにまとめる。time は 'YYYY-MM-DDTHH:MM' 形式。"""
    times: list[str] = hourly.get("time", []) or []
    series: list[float | None] = hourly.get(key, []) or []
    out: dict[str, list[float | None]] = {}
    for t, v in zip(times, series):
        day = t[:10]
        out.setdefault(day, []).append(v)
    return out


def _shape(v: Any, unit: str | None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """factor_values.values の1エントリ形（{"v":..,"unit":..,"src":"open_meteo"}）に整える。"""
    d: dict[str, Any] = {"v": v, "src": "open_meteo"}
    if unit is not None:
        d["unit"] = unit
    if extra:
        d.update(extra)
    return d


def map_response_to_factor_values(
    data: dict[str, Any], latitude: float | None
) -> dict[str, dict[str, Any]]:
    """Open-Meteo レスポンスを {value_date: {factor_key: entry}} に変換する（§5.1 マッピング）。"""
    daily = data.get("daily", {}) or {}
    hourly = data.get("hourly", {}) or {}
    days: list[str] = daily.get("time", []) or []

    sunshine: list[float | None] = daily.get("sunshine_duration", []) or []
    tmax: list[float | None] = daily.get("temperature_2m_max", []) or []
    tmin: list[float | None] = daily.get("temperature_2m_min", []) or []
    wcode: list[float | None] = daily.get("weather_code", []) or []

    pressure_by_day = _group_hourly_by_date(hourly, "surface_pressure")
    humidity_by_day = _group_hourly_by_date(hourly, "relative_humidity_2m")

    out: dict[str, dict[str, Any]] = {}
    prev_pressure: float | None = None
    for i, day in enumerate(days):
        entry: dict[str, Any] = {}

        # barometric_pressure: 日次代表値（平均）＋前日比 delta
        p_mean = _mean(pressure_by_day.get(day, []))
        if p_mean is not None:
            delta = None if prev_pressure is None else round(p_mean - prev_pressure, 2)
            entry["barometric_pressure"] = _shape(
                round(p_mean, 2), "hPa", {"delta": delta}
            )
            prev_pressure = p_mean

        # sunshine_hours: 秒 → 時間
        if i < len(sunshine) and sunshine[i] is not None:
            entry["sunshine_hours"] = _shape(round(sunshine[i] / 3600.0, 2), "hours")

        # temperature_swing: max - min
        if i < len(tmax) and i < len(tmin) and tmax[i] is not None and tmin[i] is not None:
            entry["temperature_swing"] = _shape(round(tmax[i] - tmin[i], 2), "℃")

        # weather_humidity: 湿度代表値（平均）＋ weather_code
        h_mean = _mean(humidity_by_day.get(day, []))
        wc = wcode[i] if i < len(wcode) else None
        if h_mean is not None or wc is not None:
            extra: dict[str, Any] = {}
            if wc is not None:
                extra["weather_code"] = int(wc)
            entry["weather_humidity"] = _shape(
                None if h_mean is None else round(h_mean, 1), "%", extra
            )

        # season_daylength（derived・API 不要）
        if latitude is not None:
            try:
                y, m, dd = (int(x) for x in day.split("-"))
                entry["season_daylength"] = {
                    "v": compute_season_daylength(date(y, m, dd), latitude),
                    "unit": "hours",
                    "src": "derived",
                }
            except (ValueError, TypeError):
                pass

        if entry:
            out[day] = entry
    return out


async def fetch_daily_factors(
    getter: MeteoGetter,
    lat: float,
    lon: float,
    tz: str,
    start: date,
    end: date,
    *,
    archive: bool = False,
) -> dict[str, dict[str, Any]]:
    """指定期間の日次外部指標を取得し {value_date: {factor_key: entry}} を返す（§5.1）。

    archive=True で過去補完（archive-api）。forecast は当日＋数日先を返す。
    """
    url = ARCHIVE_URL if archive else FORECAST_URL
    params: dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "daily": _DAILY_VARS,
        "hourly": _HOURLY_VARS,
        "timezone": tz,
    }
    if archive:
        params["start_date"] = start.isoformat()
        params["end_date"] = end.isoformat()
    else:
        # forecast は当日基準の相対範囲。start が過去なら archive を使う想定。
        # 直近＋数日先をカバーするため forecast_days を指定する。
        span = max((end - start).days + 1, 1)
        params["forecast_days"] = min(max(span, 1), 16)  # Open-Meteo 上限16日
    data = await getter.get_json(url, params)
    return map_response_to_factor_values(data, lat)


async def merge_factor_values(
    conn, uid: str, per_date: dict[str, dict[str, Any]]
) -> int:
    """取得した日次指標を factor_values.values に JSONB マージ保存する（§5.3・行は消さない）。

    バッチ（service_tx）文脈で呼ぶ。RLS 迂回のため **必ず user_id を明示**する（P-2）。
    既存の values を優先せず、Open-Meteo 側で上書きマージ（`values || new`）する。
    """
    import json

    count = 0
    for day, entry in per_date.items():
        if not entry:
            continue
        await conn.execute(
            """
            insert into public.factor_values (user_id, value_date, values)
            values (%(uid)s, %(d)s, %(v)s::jsonb)
            on conflict (user_id, value_date)
            do update set values = public.factor_values.values || excluded.values,
                          updated_at = now()
            """,
            {"uid": uid, "d": day, "v": json.dumps(entry)},
        )
        count += 1
    return count
