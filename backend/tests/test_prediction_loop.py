"""予測ループの一気通貫テスト（§4・完了条件）。

フェイク GPT で:
  1. 過去ログ投入（bulk）
  2. 日次予測バッチ（NL-API-16）→ predictions upsert
  3. 翌日実測登録（NL-API-06）→ 予測突合（§4.4）で誤差記録
  4. 週次ノート更新（NL-API-17）→ 新版 insert＋current 切替
  5. 現行ノート取得（NL-API-18）
さらにバッチ内部トークン（§7.2）の 401 系も検証する。
"""
from __future__ import annotations

from datetime import date, timedelta

from conftest import requires_stack


@requires_stack
def test_daily_prediction_match_and_weekly_note_loop(
    client, user_b, use_fakes, batch_headers
):
    """user_b で予測→突合→ノート更新のループが一貫して動く。"""
    fake_llm, _ = use_fakes()  # predicted_score=6 の決定的 GPT
    h = user_b["headers"]

    target = date.today() - timedelta(days=1)      # 予測対象日（未来日ガードに掛からない過去日）
    base = target - timedelta(days=1)              # 予測の as-of 日

    # 1) 過去ログ投入（base までの直近ログ）。
    records = [
        {
            "record_date": (base - timedelta(days=i)).isoformat(),
            "actual_score": 5,
            "comment": f"{i}日前のメモ",
        }
        for i in range(5)
    ]
    r = client.post("/api/records/bulk", headers=h, json={"records": records})
    assert r.status_code == 201

    # 2) 日次予測バッチ（内部トークン必須）。
    r = client.post(
        "/api/predictions/run",
        headers=batch_headers,
        json={"user_id": user_b["id"], "target_date": target.isoformat()},
    )
    assert r.status_code == 200, r.text
    run_body = r.json()
    assert run_body["ran"] == 1
    pred = run_body["results"][0]["prediction"]
    assert pred["predicted_score"] == 6  # フェイク GPT の値

    # 履歴に予測が反映される（実測はまだ null）。
    r = client.get(
        f"/api/records?from={target.isoformat()}&to={target.isoformat()}", headers=h
    )
    rows = r.json()["records"]
    assert any(row["predicted_score"] == 6 and row["actual_score"] is None for row in rows)

    # 3) 翌日実測登録 → 予測突合で誤差が記録される（§4.4）。
    r = client.post(
        "/api/records",
        headers=h,
        json={"record_date": target.isoformat(), "actual_score": 9, "comment": "よく眠れた"},
    )
    assert r.status_code == 201
    matched = r.json()["matched_prediction"]
    assert matched is not None
    assert matched["predicted_score"] == 6
    assert matched["actual_score"] == 9
    assert matched["error"] == 3      # 9 - 6
    assert matched["abs_error"] == 3

    # 4) 週次ノート更新（内部トークン必須）→ 新版作成＋current 切替。
    r = client.post(
        "/api/notes/refresh",
        headers=batch_headers,
        json={"user_id": user_b["id"], "base": date.today().isoformat()},
    )
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 1

    # 5) 現行ノート取得（NL-API-18）。
    r = client.get("/api/notes/current", headers=h)
    assert r.status_code == 200
    note = r.json()["note"]
    assert note is not None
    assert note["version"] == 1
    assert "傾向" in note["content"]  # フェイク GPT のノート本文

    # 再実行でバージョンが上がり、current は1つだけ（版管理）。
    r = client.post(
        "/api/notes/refresh",
        headers=batch_headers,
        json={"user_id": user_b["id"], "base": date.today().isoformat()},
    )
    assert r.status_code == 200
    r = client.get("/api/notes/current", headers=h)
    assert r.json()["note"]["version"] == 2


@requires_stack
def test_predictions_run_crisis_flag_propagates(client, user_a, use_fakes, batch_headers):
    """GPT の crisis_flag が predictions.crisis_flag に伝播し、ホームの crisis 案内に出る。"""
    from _fakes import FakeLLMClient

    use_fakes(llm=FakeLLMClient(predicted_score=3, crisis_flag=True))
    target = date.today() - timedelta(days=1)
    r = client.post(
        "/api/predictions/run",
        headers=batch_headers,
        json={"user_id": user_a["id"], "target_date": target.isoformat()},
    )
    assert r.status_code == 200, r.text
    assert r.json()["results"][0]["prediction"]["crisis_flag"] is True


@requires_stack
def test_batch_endpoints_require_token(client, user_a):
    """内部トークン無し／不正は 401（fail-closed・§7.2）。"""
    # トークン未設定（ヘッダ無し）
    r = client.post("/api/predictions/run", json={"user_id": user_a["id"]})
    assert r.status_code == 401
    r = client.post("/api/notes/refresh", json={"user_id": user_a["id"]})
    assert r.status_code == 401


@requires_stack
def test_batch_wrong_token_rejected(client, user_a, batch_headers):
    """正しいトークンが設定されていても、異なる値のヘッダは 401。"""
    r = client.post(
        "/api/predictions/run",
        headers={"X-Batch-Token": "wrong-token"},
        json={"user_id": user_a["id"]},
    )
    assert r.status_code == 401
