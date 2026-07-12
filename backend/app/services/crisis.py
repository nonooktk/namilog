"""危機的コメント検知（ARCHITECTURE.md §7.4）。

OR 判定（保守的＝false negative を避ける）の二段構えのうち、
ここでは (1) ルールベース（即時・入力時）の軽量マッチのみを M2 で実装する。
(2) GPT 構造化出力による crisis_flag は予測パイプライン（M3・§4.2）で加わる。

注意: 本機能は注意喚起のみで、介入・通報はしない（本人の主体性を尊重）。
窓口の具体名・電話番号の確定と文言レビューは M3（マイメロディ／シナモロール）。

入力源（シナモロール M1 レビュー必須2の反映）:
  検知の入力は体調入力のコメント（NL-API-06/07）に限らず、フィードバックチャットの
  発話（NL-API-15・M3）も対象になりうる。そのため、複数のテキストソースをまとめて
  受け取れるシグネチャにしておく（M3 でチャット発話を渡すだけで拡張できる）。
"""
from __future__ import annotations

from typing import Iterable, Sequence

# 低スコア継続の暫定トリガー閾値（§7.4 申し送り・§9-2）。
#   デザイン仕様 5.7「スコアが低い状態が続く場合」を、危機検知 OR 判定の一入力として反映する。
#   ただし「何点が何日続いたら」の確定値は M3 で窓口文言と併せてすり合わせる（キャタピー設計待ち）。
#   現時点は保守的側（早めに気づける側）に倒した暫定値を用いる。確定後にここを差し替える。
# TODO(M3・§9-2): LOW_SCORE_THRESHOLD / LOW_SCORE_MIN_DAYS の確定値をキャタピー設計に合わせて更新。
LOW_SCORE_THRESHOLD = 3   # この値「以下」を「低い」とみなす（1-10 スケール）
LOW_SCORE_MIN_DAYS = 3    # 低スコアが連続でこの日数以上続いたら陽性

# 自傷・希死念慮に関する軽量キーワード（保守的に広めに取る）。
# 文言・網羅性は M3 のレビューで精緻化する。
_CRISIS_KEYWORDS: tuple[str, ...] = (
    "死にたい",
    "消えたい",
    "自殺",
    "自傷",
    "リストカット",
    "生きていたくない",
    "いなくなりたい",
    "もう限界",
)


def _hit(text: str | None) -> bool:
    if not text:
        return False
    normalized = text.replace(" ", "").replace("　", "")
    return any(kw in normalized for kw in _CRISIS_KEYWORDS)


def detect_crisis_rule_based(text: str | None) -> bool:
    """単一テキスト（体調コメント等）に危機的兆候があるか（保守的な OR 判定の一方）。"""
    return _hit(text)


def detect_crisis_in_texts(texts: Iterable[str | None]) -> bool:
    """複数テキスト（コメント＋FB チャット発話など）をまとめて判定する。

    M3 でフィードバックチャット（NL-API-15）の発話をこの関数に渡して危機検知を拡張する。
    いずれか1つでもヒットすれば True（保守的＝false negative を避ける OR 判定）。
    """
    return any(_hit(t) for t in texts)


def detect_low_score_streak(
    recent_scores: Sequence[int | None],
    *,
    threshold: int = LOW_SCORE_THRESHOLD,
    min_days: int = LOW_SCORE_MIN_DAYS,
) -> bool:
    """低スコアの連続を危機検知の一入力として判定する（§7.4 申し送り・暫定実装）。

    `recent_scores` は「直近が先頭」（新しい順）で渡す想定。先頭から連続して threshold 以下が
    min_days 日以上続けば True。None（未記録）は連続を途切れさせる（過剰検知を避けるため）。

    注意: これは危機検知 OR 判定の一入力であり、単独で介入・通報はしない（§7.4）。閾値は暫定。
    """
    streak = 0
    for s in recent_scores:
        if s is None:
            break
        if s <= threshold:
            streak += 1
            if streak >= min_days:
                return True
        else:
            break
    return False
