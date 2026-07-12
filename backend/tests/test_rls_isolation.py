"""RLS 越境防止のテスト（P-2 / AC）。他人の記録が読めないこと。"""
from __future__ import annotations

from conftest import requires_stack


@requires_stack
def test_user_cannot_read_others_records(client, user_a, user_b):
    # A が記録を作る
    r = client.post(
        "/api/records",
        headers=user_a["headers"],
        json={"record_date": "2026-05-10", "actual_score": 4, "comment": "A の記録"},
    )
    assert r.status_code == 201

    # B は A の記録を読めない（自分の履歴だけが返る）
    r = client.get("/api/records", headers=user_b["headers"])
    assert r.status_code == 200
    comments = [row.get("comment") for row in r.json()["records"]]
    assert "A の記録" not in comments


@requires_stack
def test_user_sees_only_own_records(client, user_a):
    r = client.post(
        "/api/records",
        headers=user_a["headers"],
        json={"record_date": "2026-05-11", "actual_score": 6, "comment": "A だけの記録"},
    )
    assert r.status_code == 201
    r = client.get("/api/records?from=2026-05-11&to=2026-05-11", headers=user_a["headers"])
    assert r.status_code == 200
    rows = r.json()["records"]
    assert any(row.get("comment") == "A だけの記録" for row in rows)
