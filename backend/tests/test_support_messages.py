"""相談窓口案内文言の確定版テスト（デザイン 6.5・確定 2026-07-12）。DB 不要。

正本（デザイン仕様 6.5）の確定内容と一致していることを固定して回帰を防ぐ。
"""
from __future__ import annotations

from app.services.support_messages import (
    CRISIS_SUPPORT_CONTACTS,
    CRISIS_SUPPORT_INTRO,
    crisis_support_text,
)


def test_intro_is_confirmed_wording():
    assert CRISIS_SUPPORT_INTRO == (
        "もし今、つらい気持ちが大きくなっているなら、ひとりで抱えなくて大丈夫。"
        "よかったら話してみてね。"
    )


def test_contacts_are_confirmed_two_windows():
    # 確定・2件。番号と受付時間の短文がデザイン 6.5 と一致する。
    names = {c["name"] for c in CRISIS_SUPPORT_CONTACTS}
    assert names == {"よりそいホットライン", "こころの健康相談統一ダイヤル"}
    by_name = {c["name"]: c for c in CRISIS_SUPPORT_CONTACTS}
    assert by_name["よりそいホットライン"]["phone"] == "0120-279-338"
    assert by_name["よりそいホットライン"]["hours"] == "24時間・通話無料"
    assert by_name["こころの健康相談統一ダイヤル"]["phone"] == "0570-064-556"
    # 地域差ありのため断定的な時間表記をしない（誤案内回避）。
    assert by_name["こころの健康相談統一ダイヤル"]["hours"] == "受付時間はお住まいの地域により異なります"


def test_composed_text_contains_both_numbers():
    text = crisis_support_text()
    assert "0120-279-338" in text
    assert "0570-064-556" in text
    # 暫定表示の断り書きは確定に伴い削除されている。
    assert "暫定" not in text
