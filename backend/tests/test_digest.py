"""期間ダイジェスト API のテスト（NL-API-19・§4.6・§7.6）。

- 未認証 401（DB 不要）。
- バリデーション 422: from>to / 92日超 / 未来日（pydantic レベル）。
- 期間内実測 0 件は 422（LLM を叩かない・§3.2）。
- フェイク LLM で正常生成＋保存。2回目は保存済みを再利用（LLM 呼び出し回数で検証）。
- force で再生成（呼び出し回数が増える）。
- LLM 未設定（None）は 503 degrade。
- ガードレール（§7.6）発火時に安全文言へフォールバック。
"""
from __future__ import annotations

from conftest import requires_stack


def _seed(client, headers, records):
    """bulk 登録で期間内の実測を用意するヘルパ。"""
    r = client.post("/api/records/bulk", headers=headers, json={"records": records})
    assert r.status_code == 201, r.text


# ---- 認証（DB 不要） ----
def test_digest_requires_auth(client):
    """トークン無しは 401（§3.2）。"""
    r = client.post("/api/digest", json={"from": "2021-05-01", "to": "2021-05-31"})
    assert r.status_code == 401


# ---- バリデーション（pydantic・422） ----
@requires_stack
def test_digest_from_after_to_rejected(client, user_a):
    r = client.post(
        "/api/digest",
        headers=user_a["headers"],
        json={"from": "2021-05-31", "to": "2021-05-01"},
    )
    assert r.status_code == 422


@requires_stack
def test_digest_period_over_limit_rejected(client, user_a):
    """期間上限 92 日超は 422（§3.2 / §4.6）。約1年の期間を指定する。"""
    r = client.post(
        "/api/digest",
        headers=user_a["headers"],
        json={"from": "2021-01-01", "to": "2021-12-31"},
    )
    assert r.status_code == 422


@requires_stack
def test_digest_future_to_rejected(client, user_a):
    """to の未来日は 422（§3.2 未来日ガード）。"""
    r = client.post(
        "/api/digest",
        headers=user_a["headers"],
        json={"from": "2999-01-01", "to": "2999-01-31"},
    )
    assert r.status_code == 422


# ---- 期間内実測 0 件（422・LLM を叩かない） ----
@requires_stack
def test_digest_empty_period_rejected(client, user_a, use_fakes):
    # フェイク LLM を入れて client=None（503）と区別する（0 件は 422 が期待値）。
    use_fakes()
    r = client.post(
        "/api/digest",
        headers=user_a["headers"],
        json={"from": "2019-01-01", "to": "2019-03-01"},
    )
    assert r.status_code == 422


# ---- 正常生成＋保存、2回目キャッシュ ----
@requires_stack
def test_digest_generate_and_cache(client, user_a, use_fakes):
    fake, _ = use_fakes()
    h = user_a["headers"]
    _seed(
        client,
        h,
        [
            {"record_date": "2021-05-01", "actual_score": 8, "comment": "よく眠れた"},
            {"record_date": "2021-05-02", "actual_score": 6, "comment": "ふつう"},
            {"record_date": "2021-05-03", "actual_score": 3, "comment": "だるい"},
        ],
    )

    # 1回目: 生成。
    r = client.post(
        "/api/digest", headers=h, json={"from": "2021-05-01", "to": "2021-05-31"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cached"] is False
    assert isinstance(body["summary"], str) and body["summary"]
    assert isinstance(body["good_days"], list)
    assert isinstance(body["bad_days"], list)
    calls_after_first = len(fake.json_calls)
    assert calls_after_first == 1

    # 2回目（同一期間・force なし）: 保存済みを再利用し、LLM を叩き直さない。
    r2 = client.post(
        "/api/digest", headers=h, json={"from": "2021-05-01", "to": "2021-05-31"}
    )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["cached"] is True
    assert body2["summary"] == body["summary"]
    assert len(fake.json_calls) == calls_after_first  # 呼び出し回数は増えない（キャッシュ）。


# ---- force で再生成 ----
@requires_stack
def test_digest_force_regenerates(client, user_a, use_fakes):
    fake, _ = use_fakes()
    h = user_a["headers"]
    _seed(
        client,
        h,
        [
            {"record_date": "2021-08-01", "actual_score": 7, "comment": "散歩した"},
            {"record_date": "2021-08-02", "actual_score": 4, "comment": "疲れ気味"},
        ],
    )
    period = {"from": "2021-08-01", "to": "2021-08-31"}

    r1 = client.post("/api/digest", headers=h, json=period)
    assert r1.status_code == 200
    assert r1.json()["cached"] is False
    assert len(fake.json_calls) == 1

    # force なし → キャッシュ（呼び出し増えない）。
    r2 = client.post("/api/digest", headers=h, json=period)
    assert r2.json()["cached"] is True
    assert len(fake.json_calls) == 1

    # force=true → 再生成（呼び出しが増える）。
    r3 = client.post("/api/digest", headers=h, json={**period, "force": True})
    assert r3.status_code == 200
    assert r3.json()["cached"] is False
    assert len(fake.json_calls) == 2


# ---- LLM 未設定（None）は 503 degrade（生成が必要になった時点で判定・#1） ----
@requires_stack
def test_digest_degrade_when_llm_unset(client, user_a):
    """use_fakes を入れない＝get_llm_client が None。実測はあるが未生成のため 503（§7.5）。"""
    h = user_a["headers"]
    # 実測を用意（0 件だと 422 になるため）。キャッシュの無い専用期間を使う。
    _seed(client, h, [{"record_date": "2022-01-05", "actual_score": 5, "comment": "ふつう"}])
    r = client.post("/api/digest", headers=h, json={"from": "2022-01-01", "to": "2022-01-31"})
    assert r.status_code == 503


# ---- キャッシュは LLM 可用性に依存せず返せる（#1・§2.12） ----
@requires_stack
def test_digest_cache_returned_even_without_llm(client, user_a, use_fakes):
    """保存済みダイジェストは、その後 LLM 未設定でも 200 で再利用できる（#1）。"""
    h = user_a["headers"]
    period = {"from": "2022-02-01", "to": "2022-02-28"}
    _seed(client, h, [{"record_date": "2022-02-10", "actual_score": 7, "comment": "散歩"}])

    # まずフェイク LLM で生成・保存。
    fake, _ = use_fakes()
    r1 = client.post("/api/digest", headers=h, json=period)
    assert r1.status_code == 200 and r1.json()["cached"] is False

    # フェイクを外す（get_llm_client=None 相当）。それでもキャッシュは返る。
    from app.deps.providers import get_llm_client
    from app.main import app

    app.dependency_overrides[get_llm_client] = lambda: None
    try:
        r2 = client.post("/api/digest", headers=h, json=period)
        assert r2.status_code == 200
        assert r2.json()["cached"] is True
    finally:
        app.dependency_overrides.pop(get_llm_client, None)


# ---- LLM 通信エラー・タイムアウト・不正レスポンスは 503 へ degrade（#2・§7.5） ----
@requires_stack
def test_digest_llm_error_degrades(client, user_a, use_fakes):
    from _fakes import FakeLLMClient

    h = user_a["headers"]
    _seed(client, h, [{"record_date": "2022-03-05", "actual_score": 6, "comment": "ふつう"}])
    # complete_json（digest）で例外を送出するフェイク（通信障害等の再現）。
    use_fakes(llm=FakeLLMClient(raise_on_digest=RuntimeError("boom: connection reset")))
    r = client.post("/api/digest", headers=h, json={"from": "2022-03-01", "to": "2022-03-31"})
    assert r.status_code == 503


# ---- 期間外・幻覚日付の good_days/bad_days は除外（#4・§4.6） ----
@requires_stack
def test_digest_filters_out_of_period_dates(client, user_a, use_fakes):
    from _fakes import FakeLLMClient

    h = user_a["headers"]
    _seed(
        client,
        h,
        [
            {"record_date": "2022-05-01", "actual_score": 8, "comment": "よい"},
            {"record_date": "2022-05-02", "actual_score": 3, "comment": "つらい"},
        ],
    )
    # good_days に「実在する日(2022-05-01)」と「期間外の幻覚日(2099-12-31)」を混在させる。
    fake = FakeLLMClient(
        digest_good_days=[
            {"date": "2022-05-01", "note": "調子よし", "coping": "散歩した"},
            {"date": "2099-12-31", "note": "幻覚の日", "coping": "存在しない"},
        ],
        digest_bad_days=[
            {"date": "2022-05-02", "note": "だるい", "coping": "休んだ"},
            {"date": "2000-01-01", "note": "期間外", "coping": "無視されるべき"},
        ],
    )
    use_fakes(llm=fake)
    r = client.post("/api/digest", headers=h, json={"from": "2022-05-01", "to": "2022-05-31"})
    assert r.status_code == 200, r.text
    body = r.json()
    # 実測のある期間内日付のみ残る。幻覚・期間外は除外。
    assert [d["date"] for d in body["good_days"]] == ["2022-05-01"]
    assert [d["date"] for d in body["bad_days"]] == ["2022-05-02"]


# ---- ガードレール（§7.6）発火時のフォールバック ----
@requires_stack
def test_digest_guardrail_fallback(client, user_a, use_fakes):
    from _fakes import FakeLLMClient

    from app.services.guardrails import SAFE_DIGEST_FALLBACK

    # 医療断定・服薬指示を含む不適切な出力を返すフェイク。
    unsafe = FakeLLMClient(
        digest_summary="あなたはうつ病です。必ず治ります。",
        digest_good_days=[
            {"date": "2021-09-01", "note": "薬をやめてください", "coping": "受診すべき"}
        ],
        digest_bad_days=[],
    )
    use_fakes(llm=unsafe)
    h = user_a["headers"]
    _seed(
        client,
        h,
        [{"record_date": "2021-09-01", "actual_score": 5, "comment": "ふつう"}],
    )

    r = client.post(
        "/api/digest", headers=h, json={"from": "2021-09-01", "to": "2021-09-30"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # summary は安全文言へフォールバックする。
    assert body["summary"] == SAFE_DIGEST_FALLBACK
    # good_days の note/coping も後段フィルタで安全文言へ。
    assert body["good_days"][0]["note"] == SAFE_DIGEST_FALLBACK
    assert body["good_days"][0]["coping"] == SAFE_DIGEST_FALLBACK
