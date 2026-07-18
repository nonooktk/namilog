"""MI セッションの安全性・要約保存・境界の回帰テスト。"""
from __future__ import annotations

import asyncio

from conftest import requires_stack

from app.services.mi_safety import check_output
from app.services.mi_session import BOUNDARY_TURN, boundary_suggested, extract_state_update, merge_state


def test_mi_state_update_failure_keeps_previous_state():
    previous = {"focus": "睡眠", "turn_count": 2}
    visible, update = extract_state_update("受け止めています。<state_update>{not json}</state_update>")
    assert visible == "受け止めています。"
    assert update is None
    assert merge_state(previous, update) == previous


def test_mi_boundary_turn():
    assert boundary_suggested(BOUNDARY_TURN - 1) is False
    assert boundary_suggested(BOUNDARY_TURN) is True


def test_mi_output_gate_discards_crisis_and_medical_assertion():
    from _fakes import FakeLLMClient

    crisis = asyncio.run(check_output("死にたいなら一人で考えましょう。", {}, FakeLLMClient()))
    medical = asyncio.run(check_output("あなたはうつ病です。", {}, FakeLLMClient()))
    assert crisis[0] is True and "0120-279-338" in crisis[1]
    assert medical[0] is True and "0120-279-338" in medical[1]


def test_mi_output_gate_fails_closed_when_crisis_judgment_fails():
    from _fakes import FakeLLMClient

    class BrokenCrisisClient(FakeLLMClient):
        async def complete_json(self, **kwargs):
            raise RuntimeError("judge unavailable")

    discarded, replacement = asyncio.run(
        check_output("落ち着いて話していきましょう。", {}, BrokenCrisisClient())
    )
    assert discarded is True
    assert "0120-279-338" in replacement


@requires_stack
def test_mi_roundtrip_crisis_and_summary_storage(client, user_a, use_fakes):
    from _fakes import FakeLLMClient

    # state_update を返すフェイクにして、逐語でない user summary の保存を検証する。
    fake = FakeLLMClient(reply_text=(
        "話してくださって、気持ちを整理したい思いがあるのですね。"
        "今いちばん大事にしたいことは何でしょうか。"
        '<state_update>{"focus":"生活リズム","user_utterance_summary":"生活リズムを整えたい気持ち",'
        '"assistant_response_summary":"気持ちを聞き返し、焦点を尋ねた"}</state_update>'
    ))
    use_fakes(llm=fake)
    h = user_a["headers"]
    start = client.post("/api/mi/session", headers=h, json={"theme": "生活リズム"})
    assert start.status_code == 201
    raw_user = "昨夜は眠れなくて、明日も仕事なのが不安です"
    sent = client.post("/api/mi/message", headers=h, json={"content": raw_user})
    assert sent.status_code == 200
    assert sent.json()["crisis_notice"] is False
    got = client.get("/api/mi/session", headers=h).json()
    stored_user = next(row for row in got["messages"] if row["role"] == "user")
    assert stored_user["content"] != raw_user
    assert stored_user["is_verbatim"] is False

    # 入力側ゲートは応答生成なしで停止し、定型窓口だけを全文保存する。
    crisis = client.post("/api/mi/message", headers=h, json={"content": "もう消えたいです"})
    assert crisis.status_code == 200
    assert crisis.json()["crisis_notice"] is True
    assert "0120-279-338" in crisis.json()["assistant_message"]["content"]


@requires_stack
def test_mi_rls_does_not_expose_other_users_session(client, user_a, user_b, use_fakes):
    use_fakes()
    assert client.post("/api/mi/session", headers=user_a["headers"], json={}).status_code == 201
    response = client.get("/api/mi/session", headers=user_b["headers"])
    assert response.status_code == 200
    assert response.json()["session"] is None
