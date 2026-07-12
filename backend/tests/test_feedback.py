"""FB チャットのテスト（NL-API-14 / 15・§7.4・§7.6）。

- user 発話保存 → assistant 応答保存 → 履歴取得。
- FB 発話も危機検知の入力源（M1 必須2）: 危機語を含む発話で crisis_notice が立ち、
  応答に相談窓口文言が添えられる。
"""
from __future__ import annotations

from conftest import requires_stack


@requires_stack
def test_feedback_roundtrip(client, user_a, use_fakes):
    fake_llm, _ = use_fakes()
    h = user_a["headers"]

    r = client.post("/api/feedback", headers=h, json={"content": "今日はよく眠れました"})
    assert r.status_code == 201
    body = r.json()
    assert body["user_message"]["role"] == "user"
    assert body["assistant_message"]["role"] == "assistant"
    assert body["crisis_notice"] is False
    assert body["assistant_message"]["content"]  # 応答が入っている

    # 履歴取得（user→assistant の順で並ぶ）
    r = client.get("/api/feedback", headers=h)
    assert r.status_code == 200
    msgs = r.json()["messages"]
    roles = [m["role"] for m in msgs]
    assert "user" in roles and "assistant" in roles


@requires_stack
def test_feedback_crisis_detection_on_user_utterance(client, user_a, use_fakes):
    """FB の user 発話が危機検知の入力源（M1 必須2・§7.4）。"""
    use_fakes()
    r = client.post(
        "/api/feedback", headers=user_a["headers"], json={"content": "もう消えたい気持ちです"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["crisis_notice"] is True
    # 応答に確定版の相談窓口（よりそいホットライン 0120-279-338）が添えられる（デザイン 6.5）。
    content = body["assistant_message"]["content"]
    assert "0120-279-338" in content
    assert "0570-064-556" in content


@requires_stack
def test_feedback_gpt_crisis_detection_without_keyword(client, user_a, use_fakes):
    """キーワード不一致でも GPT 文脈判定が陽性なら crisis になる（§7.4-3・R1）。"""
    from _fakes import FakeLLMClient

    # ルールベースには当たらない文面だが GPT が危機と判定するフェイク。
    use_fakes(llm=FakeLLMClient(gpt_crisis_judgment=True))
    r = client.post(
        "/api/feedback",
        headers=user_a["headers"],
        json={"content": "もうなにもかも投げ出してしまいたい気分です"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["crisis_notice"] is True
    # 応答に確定版の窓口が添えられる。
    assert "0120-279-338" in body["assistant_message"]["content"]


@requires_stack
def test_feedback_content_validation(client, user_a):
    # 空文字は 422
    r = client.post("/api/feedback", headers=user_a["headers"], json={"content": ""})
    assert r.status_code == 422
