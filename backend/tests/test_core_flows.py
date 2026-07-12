"""M2 コアフローのテスト: プロフィール・一括入力・履歴結合・ホーム degrade。"""
from __future__ import annotations

from conftest import requires_stack


@requires_stack
def test_profile_update_and_get(client, user_a):
    h = user_a["headers"]
    r = client.put(
        "/api/profile",
        headers=h,
        json={
            "display_name": "テスト太郎",
            "latitude": 35.68,
            "longitude": 139.76,
            "timezone": "Asia/Tokyo",
            "agree_medical_disclaimer": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["medical_disclaimer_agreed_at"] is not None  # 同意時刻が記録される

    r = client.get("/api/profile", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["display_name"] == "テスト太郎"
    assert body["onboarded_at"] is not None


@requires_stack
def test_bulk_import_and_history_join(client, user_a):
    h = user_a["headers"]
    r = client.post(
        "/api/records/bulk",
        headers=h,
        json={
            "records": [
                {"record_date": "2026-03-01", "actual_score": 5, "comment": "三月一日"},
                {"record_date": "2026-03-02", "actual_score": 8, "comment": "三月二日"},
                {"record_date": "2026-03-03", "actual_score": 3, "comment": "三月三日"},
            ]
        },
    )
    assert r.status_code == 201
    assert r.json()["saved"] == 3

    # 履歴一覧（実測・予測の結合。予測は未生成なので predicted は null）
    r = client.get("/api/records?from=2026-03-01&to=2026-03-03", headers=h)
    assert r.status_code == 200
    rows = r.json()["records"]
    dates = {row["date"] for row in rows}
    assert {"2026-03-01", "2026-03-02", "2026-03-03"} <= dates
    for row in rows:
        assert row["predicted_score"] is None  # M2 では予測未生成

    # 波グラフ用時系列（昇順）
    r = client.get("/api/history/series?from=2026-03-01&to=2026-03-03", headers=h)
    assert r.status_code == 200
    series = r.json()["series"]
    assert [s["date"] for s in series] == ["2026-03-01", "2026-03-02", "2026-03-03"]
    assert series[1]["actual"] == 8


@requires_stack
def test_home_degrades_when_no_prediction(client, user_a):
    """予測が未生成なら degrade メッセージ（§7.5）。"""
    r = client.get("/api/home", headers=user_a["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["tomorrow"]["prediction"] is None
    assert body["notice"] == "本日の予測はまだありません"
    assert body["crisis_notice"] is False


@requires_stack
def test_crisis_notice_on_record(client, user_a):
    """危機的コメントで crisis_notice が立つ（ルールベース・保守的）。"""
    r = client.post(
        "/api/records",
        headers=user_a["headers"],
        json={"record_date": "2026-02-15", "actual_score": 2, "comment": "もう消えたい"},
    )
    assert r.status_code == 201
    assert r.json()["crisis_notice"] is True


@requires_stack
def test_factor_values_merge_accumulates(client, user_a):
    """手入力指標値は JSONB マージで蓄積される（NL-API-08）。"""
    h = user_a["headers"]
    client.put("/api/factor-values/2026-02-20", headers=h, json={"values": {"sleep": 7.0}})
    r = client.put(
        "/api/factor-values/2026-02-20", headers=h, json={"values": {"medication": "ok"}}
    )
    assert r.status_code == 200
    values = r.json()["values"]
    assert values["sleep"]["v"] == 7.0  # 前回の値が残っている
    assert values["medication"]["v"] == "ok"
