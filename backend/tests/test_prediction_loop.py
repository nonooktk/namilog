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

import asyncio
from datetime import date, datetime, timedelta, timezone

import psycopg

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

    # 6) 冪等化（P1）: 同一週の再実行は新版を作らずスキップ（updated=0・version 据え置き）。
    r = client.post(
        "/api/notes/refresh",
        headers=batch_headers,
        json={"user_id": user_b["id"], "base": date.today().isoformat()},
    )
    assert r.status_code == 200
    assert r.json()["updated"] == 0  # 同一週に既に weekly_batch 版があるためスキップ
    r = client.get("/api/notes/current", headers=h)
    assert r.json()["note"]["version"] == 1  # 版は増えない

    # force=True なら同一週でも強制的に新版を作る（手動再生成・補正用）。current は1つだけ。
    r = client.post(
        "/api/notes/refresh",
        headers=batch_headers,
        json={"user_id": user_b["id"], "base": date.today().isoformat(), "force": True},
    )
    assert r.status_code == 200
    assert r.json()["updated"] == 1
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


# 冪等判定の TZ 境界マーカー（掃除対象を自テストの挿入行だけに限定するための目印）。
_TZ_MARKER = "__tz_boundary_regression__"


@requires_stack
def test_weekly_note_idempotency_survives_utc_day_boundary(user_a, db_url):
    """週次ノート冪等判定が UTC/JST 日跨ぎでも同一週を正しく検出する（回帰・2026-07-13 実スタック検証）。

    バグ再現条件を決定的に固定する（実時刻・ホスト tz に依存しない）:
      APP_DEFAULT_TZ=Asia/Tokyo で「JST 月曜 05:00」に作られた版は、UTC では前日（日曜）夜になる。
      修正前の `created_at >= <date>` 比較はこの版を当該週の外と誤判定し、同一週に版を重複生成した。
      修正後は created_at を JST 暦日へ正規化して比較するため、同一週として検出（True）される。
    """
    uid = user_a["id"]
    # JST 月曜 2026-07-13 05:00 = UTC 2026-07-12(日) 20:00。base は同じ週の JST 月曜。
    created_utc = datetime(2026, 7, 12, 20, 0, tzinfo=timezone.utc)
    base_this_week = date(2026, 7, 13)          # JST 月曜（この週）
    base_prev_week = base_this_week - timedelta(days=7)  # 前週の月曜（窓の外を確認）

    async def _run() -> tuple[bool, bool]:
        # db_url は postgres 接続（BYPASSRLS）。RLS 迂回で created_at を明示挿入できる。
        aconn = await psycopg.AsyncConnection.connect(db_url, autocommit=True)
        try:
            # 遅延 import: モジュール読み込み順（conftest の env 確定）後に app を触る。
            from app.services.notes import _has_weekly_note_this_week

            # FK 担保（profiles 行が無ければ id のみで用意）。
            await aconn.execute(
                "insert into public.profiles (id) values (%s) on conflict (id) do nothing",
                (uid,),
            )
            # 自テストの残骸を掃除（決定性）。
            await aconn.execute(
                "delete from public.prediction_notes where user_id=%s and content=%s",
                (uid, _TZ_MARKER),
            )
            # 既存版と version 衝突しないよう次番号を採番。
            row = await (
                await aconn.execute(
                    "select coalesce(max(version),0)+1 from public.prediction_notes where user_id=%s",
                    (uid,),
                )
            ).fetchone()
            next_version = row[0]
            # created_at を明示指定（is_current=false で uq_notes_current 制約を回避）。
            await aconn.execute(
                """
                insert into public.prediction_notes
                    (user_id, version, content, is_current, source, created_at)
                values (%s, %s, %s, false, 'weekly_batch', %s)
                """,
                (uid, next_version, _TZ_MARKER, created_utc),
            )
            in_week = await _has_weekly_note_this_week(aconn, uid, base_this_week)
            out_week = await _has_weekly_note_this_week(aconn, uid, base_prev_week)
            # 後片付け。
            await aconn.execute(
                "delete from public.prediction_notes where user_id=%s and content=%s",
                (uid, _TZ_MARKER),
            )
            return in_week, out_week
        finally:
            await aconn.close()

    in_week, out_week = asyncio.run(_run())
    assert in_week is True   # 修正の要点: UTC 前日夜の版でも JST 正規化で「同一週」を検出
    assert out_week is False  # 窓の外（前週基準）は誤検出しない


@requires_stack
def test_batch_wrong_token_rejected(client, user_a, batch_headers):
    """正しいトークンが設定されていても、異なる値のヘッダは 401。"""
    r = client.post(
        "/api/predictions/run",
        headers={"X-Batch-Token": "wrong-token"},
        json={"user_id": user_a["id"]},
    )
    assert r.status_code == 401
