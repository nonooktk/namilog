"""バリデーションのテスト（§3.2）。スコア 1–10、factor_keys ちょうど3件。

happy path は DB を要するため requires_stack。範囲外・件数不一致の 422 は
pydantic レベルで弾かれるが、認証は通す必要があるため user_a を使う。
"""
from __future__ import annotations

from conftest import requires_stack


@requires_stack
def test_score_out_of_range_rejected(client, user_a):
    for bad in (0, 11, -3):
        r = client.post(
            "/api/records",
            headers=user_a["headers"],
            json={"record_date": "2026-07-01", "actual_score": bad, "comment": "x"},
        )
        assert r.status_code == 422, f"score={bad} は 422 のはず"


@requires_stack
def test_score_within_range_accepted(client, user_a):
    r = client.post(
        "/api/records",
        headers=user_a["headers"],
        json={"record_date": "2026-06-01", "actual_score": 7, "comment": "ふつう"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["record"]["actual_score"] == 7


@requires_stack
def test_future_record_date_rejected(client, user_a):
    """未来日の record_date は 422（シナモロール M1 レビュー推奨の未来日ガード）。"""
    r = client.post(
        "/api/records",
        headers=user_a["headers"],
        json={"record_date": "2999-01-01", "actual_score": 5, "comment": "未来"},
    )
    assert r.status_code == 422


@requires_stack
def test_factor_keys_must_be_exactly_three(client, user_a):
    # 2件 → 422
    r = client.put(
        "/api/factors/selection",
        headers=user_a["headers"],
        json={"factor_keys": ["barometric_pressure", "sleep"]},
    )
    assert r.status_code == 422
    # 4件 → 422
    r = client.put(
        "/api/factors/selection",
        headers=user_a["headers"],
        json={"factor_keys": ["barometric_pressure", "sleep", "medication", "activity_steps"]},
    )
    assert r.status_code == 422
    # 重複を含む3件 → 422
    r = client.put(
        "/api/factors/selection",
        headers=user_a["headers"],
        json={"factor_keys": ["sleep", "sleep", "medication"]},
    )
    assert r.status_code == 422


@requires_stack
def test_factor_keys_unknown_key_rejected(client, user_a):
    r = client.put(
        "/api/factors/selection",
        headers=user_a["headers"],
        json={"factor_keys": ["barometric_pressure", "sleep", "no_such_key"]},
    )
    assert r.status_code == 400
