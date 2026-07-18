"""MI の状態、非表示 state_update、セッション境界の純粋ロジック。"""
from __future__ import annotations

import json
import re
from typing import Any

BOUNDARY_TURN = 15
STATE_UPDATE_RE = re.compile(r"<state_update>\s*(.*?)\s*</state_update>", re.DOTALL | re.IGNORECASE)


def boundary_suggested(turn_count: int) -> bool:
    """15ターン以降は、区切りや要約を提案する。"""
    return turn_count >= BOUNDARY_TURN


def extract_state_update(reply_text: str) -> tuple[str, dict[str, Any] | None]:
    """タグを表示本文から除去し、JSONが不正なら state を変更しない。"""
    match = STATE_UPDATE_RE.search(reply_text or "")
    visible = STATE_UPDATE_RE.sub("", reply_text or "").strip()
    if not match:
        return visible, None
    try:
        value = json.loads(match.group(1))
    except (TypeError, json.JSONDecodeError):
        return visible, None
    return visible, value if isinstance(value, dict) else None


def merge_state(previous: dict[str, Any] | None, update: dict[str, Any] | None) -> dict[str, Any]:
    """差分だけを浅くマージする。不正更新は前状態をそのまま返す。"""
    merged = dict(previous or {})
    if update:
        merged.update({k: v for k, v in update.items() if k not in {"user_utterance_summary", "assistant_response_summary"}})
    return merged


def summary_from_update(update: dict[str, Any] | None, key: str, fallback: str) -> str:
    """逐語を永続化しないため、モデル提供の要約だけを採用する。"""
    if update and isinstance(update.get(key), str) and update[key].strip():
        return update[key].strip()[:1000]
    return fallback
