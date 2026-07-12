"""危機検知のユニットテスト（§7.4）。DB 不要。"""
from __future__ import annotations

import asyncio

from app.services.crisis import (
    detect_crisis_in_texts,
    detect_crisis_llm,
    detect_crisis_rule_based,
    detect_low_score_streak,
)


def test_rule_based_hits_keyword_with_spaces():
    assert detect_crisis_rule_based("もう 消え たい") is True
    assert detect_crisis_rule_based("今日は元気です") is False
    assert detect_crisis_rule_based(None) is False


def test_rule_based_hiragana_and_katakana_variants():
    """漢字だけでなく、ひらがな・カタカナ異形も拾う（P3・保守的拡充）。"""
    assert detect_crisis_rule_based("もうしにたい") is True          # ひらがな
    assert detect_crisis_rule_based("きえたい") is True              # ひらがな
    assert detect_crisis_rule_based("シニタイ") is True              # カタカナ→ひらがな寄せ
    assert detect_crisis_rule_based("リスカしてしまった") is True     # 略語
    assert detect_crisis_rule_based("死んだ方が楽かも") is True
    assert detect_crisis_rule_based("もうげんかいです") is True
    # 通常の前向き文は誤検知しない
    assert detect_crisis_rule_based("今日は買い物に出かけて元気になった") is False


def test_detect_crisis_llm_degrades_without_client():
    """LLM 未設定（None）はルールベースのみに degrade（False を返す）。"""
    assert asyncio.run(detect_crisis_llm(None, "つらい")) is False
    assert asyncio.run(detect_crisis_llm(None, None)) is False


def test_detect_crisis_llm_uses_gpt_judgment():
    """GPT 文脈判定が陽性なら True（キーワード不一致でも拾える）。"""
    from _fakes import FakeLLMClient

    # キーワードに一致しない文脈的表現を GPT が陽性判定するケース。
    fake_pos = FakeLLMClient(gpt_crisis_judgment=True)
    fake_neg = FakeLLMClient(gpt_crisis_judgment=False)
    assert asyncio.run(detect_crisis_llm(fake_pos, "もう全部投げ出してしまいたい")) is True
    assert asyncio.run(detect_crisis_llm(fake_neg, "少し疲れました")) is False
    # 空テキストは呼ばずに False。
    assert asyncio.run(detect_crisis_llm(fake_pos, "")) is False


def test_multiple_sources_or():
    # FB 発話が入力源に含まれる（M1 必須2）
    assert detect_crisis_in_texts(["元気", "自傷してしまった"]) is True
    assert detect_crisis_in_texts(["元気", "散歩した"]) is False


def test_low_score_streak_provisional():
    # 新しい順で threshold(3)以下が min_days(3)連続 → True
    assert detect_low_score_streak([2, 3, 1, 8, 9]) is True
    # 2日しか続かない → False
    assert detect_low_score_streak([2, 3, 8, 1, 1]) is False
    # None は連続を途切れさせる（過剰検知を避ける）
    assert detect_low_score_streak([2, None, 2, 2]) is False
    # 高スコアが先頭 → False
    assert detect_low_score_streak([7, 2, 2, 2]) is False
