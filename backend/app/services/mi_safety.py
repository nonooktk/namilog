"""MI 応答の第二安全ゲート。判定不能時も窓口案内へ倒す。"""
from __future__ import annotations

from .crisis import detect_crisis_in_texts, detect_crisis_llm
from .guardrails import sanitize_advice
from .llm import LLMClient
from .mi_session import extract_state_update
from .support_messages import crisis_support_text


async def check_output(reply_text: str, state: dict, client: LLMClient | None) -> tuple[bool, str]:
    """(discard, visible_reply)。危機・医療断定・判定障害は本文を破棄する。"""
    try:
        visible, _ = extract_state_update(reply_text)
        if not visible:
            return True, crisis_support_text()
        # ルールと LLM の二重判定。LLM が無い/障害なら MI 自体は開始しない設計なので安全側。
        if detect_crisis_in_texts([visible]) or await detect_crisis_llm(
            client, visible, fail_closed=True
        ):
            return True, crisis_support_text()
        sanitized, changed = sanitize_advice(visible)
        if changed:
            return True, crisis_support_text()
        # 危機語を含むのに窓口・安全確認が無い応答は、曖昧でも継続しない。
        risky = ("死", "自傷", "DV", "虐待", "過量", "離脱")
        if any(word in visible for word in risky):
            return True, crisis_support_text()
        return False, sanitized
    except Exception:  # noqa: BLE001 安全判定の障害は fail closed
        return True, crisis_support_text()
