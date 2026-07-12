"""指標入れ替えのテスト（P-3 / §5.3）。

- 入れ替えても external_factors の行は消えず期間で管理される（is_active 切替）。
- 入れ替えても過去の factor_values（蓄積済みの指標値）は一切消えない。
"""
from __future__ import annotations

from conftest import requires_stack


@requires_stack
def test_selection_swap_keeps_history_and_values(client, user_a):
    h = user_a["headers"]

    # 手入力指標値を蓄積（sleep を含む日次値）
    r = client.put(
        "/api/factor-values/2026-04-01",
        headers=h,
        json={"values": {"sleep": 6.5, "medication": "ok"}},
    )
    assert r.status_code == 200

    # 初期選定: barometric_pressure / sleep / medication
    r = client.put(
        "/api/factors/selection",
        headers=h,
        json={"factor_keys": ["barometric_pressure", "sleep", "medication"]},
    )
    assert r.status_code == 200
    active_keys = {a["factor_key"] for a in r.json()["active"]}
    assert active_keys == {"barometric_pressure", "sleep", "medication"}

    # 入れ替え: sleep / medication を外し、sunshine_hours / activity_steps を入れる
    r = client.put(
        "/api/factors/selection",
        headers=h,
        json={"factor_keys": ["barometric_pressure", "sunshine_hours", "activity_steps"]},
    )
    assert r.status_code == 200
    body = r.json()
    active_keys = {a["factor_key"] for a in body["active"]}
    assert active_keys == {"barometric_pressure", "sunshine_hours", "activity_steps"}
    assert len(body["active"]) == 3  # アクティブは常にちょうど3件

    # 履歴: 外した sleep / medication の行は「消えず」非アクティブとして残る
    history_keys = {hh["factor_key"] for hh in body["history"]}
    assert "sleep" in history_keys
    assert "medication" in history_keys
    deactivated = {hh["factor_key"] for hh in body["history"] if not hh["is_active"]}
    assert {"sleep", "medication"} <= deactivated

    # 過去の factor_values は削除されていない（sleep の値がそのまま残る）
    r = client.get("/api/records", headers=h)  # 存在確認は values 側 API で
    # factor_values は selection API では返さないため、再取得で確認する
    r = client.put(
        "/api/factor-values/2026-04-01",
        headers=h,
        json={"values": {"activity_steps": 8000}},  # マージ（既存 sleep を消さない）
    )
    assert r.status_code == 200
    values = r.json()["values"]
    assert "sleep" in values, "過去に蓄積した sleep の値が消えている（P-3 違反）"
    assert values["sleep"]["v"] == 6.5
    assert "activity_steps" in values  # マージで追記されている
