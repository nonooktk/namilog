"""AI 入れ替え提案のテスト（NL-API-13）。決定的ヒューリスティック。"""
from __future__ import annotations

from conftest import requires_stack


@requires_stack
def test_suggest_returns_non_active_key(client, user_a):
    h = user_a["headers"]
    # 3指標を選定しておく。
    client.put(
        "/api/factors/selection",
        headers=h,
        json={"factor_keys": ["barometric_pressure", "sunshine_hours", "sleep"]},
    )
    r = client.post("/api/factors/suggest", headers=h)
    assert r.status_code == 200
    body = r.json()
    # 提案キーはアクティブでない指標であること（採否は本人）。
    assert body["suggested_key"] is not None
    assert body["suggested_key"] not in body["current_keys"]
    assert isinstance(body["reason"], str) and body["reason"]
