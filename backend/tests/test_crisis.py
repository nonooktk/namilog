"""危機検知のユニットテスト（§7.4）。DB 不要。"""
from __future__ import annotations

from app.services.crisis import (
    detect_crisis_in_texts,
    detect_crisis_rule_based,
    detect_low_score_streak,
)


def test_rule_based_hits_keyword_with_spaces():
    assert detect_crisis_rule_based("もう 消え たい") is True
    assert detect_crisis_rule_based("今日は元気です") is False
    assert detect_crisis_rule_based(None) is False


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
