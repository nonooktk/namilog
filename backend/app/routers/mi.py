"""MI セッション API。FB チャットとはテーブル、プロンプト、経路を共有しない。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..config import settings
from ..db import user_tx
from ..deps.auth import get_current_user
from ..deps.providers import get_llm_client
from ..schemas import MiMessageIn, MiSessionStartIn
from ..services.crisis import detect_crisis_in_texts, detect_crisis_llm
from ..services.guardrails import wrap_user_data
from ..services.llm import LLMClient
from ..services.mi_prompt import build_mi_system_prompt
from ..services.mi_safety import check_output
from ..services.mi_session import boundary_suggested, extract_state_update, merge_state, summary_from_update
from ..services.support_messages import crisis_support_text

router = APIRouter(prefix="/api/mi", tags=["mi"])
_CONTEXT_LIMIT = 12
_UNAVAILABLE = "この機能はいま利用できません。時間をおいてからお試しください。"


async def _active(conn, uid: str):
    cur = await conn.execute("select * from public.mi_sessions where user_id = %(uid)s and status = 'active' order by updated_at desc limit 1", {"uid": uid})
    return await cur.fetchone()


@router.get("/session")
async def get_session(uid: str = Depends(get_current_user), limit: int = Query(default=50, ge=1, le=200)):
    async with user_tx(uid) as conn:
        session = await _active(conn, uid)
        if not session:
            return {"session": None, "messages": []}
        cur = await conn.execute("select id, session_id, role, content, is_verbatim, turn_index, created_at from public.mi_messages where session_id = %(sid)s and user_id = %(uid)s order by turn_index, created_at limit %(lim)s", {"sid": session["id"], "uid": uid, "lim": limit})
        messages = await cur.fetchall()
    return {"session": session, "messages": messages}


@router.post("/session", status_code=status.HTTP_201_CREATED)
async def start_session(body: MiSessionStartIn, uid: str = Depends(get_current_user), client: LLMClient | None = Depends(get_llm_client)):
    if client is None:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE)
    async with user_tx(uid) as conn:
        existing = await _active(conn, uid)
        if existing:
            return {"session": existing, "assistant_message": None, "existing": True}
        cur = await conn.execute("insert into public.mi_sessions (user_id, theme) values (%(uid)s, %(theme)s) returning *", {"uid": uid, "theme": body.theme})
        session = await cur.fetchone()
    # LLM は tx 外。初回発話も state_update 形式を要求する。
    try:
        raw = await client.complete_text(system=build_mi_system_prompt({"turn_count": 0, "theme": body.theme}), user=wrap_user_data(body.theme or "話したいテーマはまだ決まっていません。", "セッションのテーマ"), max_tokens=400, model=settings.mi_model)
        discard, reply = await check_output(raw, {}, client)
    except Exception:  # noqa: BLE001 MI は定型会話へ degrade しない
        raise HTTPException(status_code=503, detail=_UNAVAILABLE) from None
    visible, update = extract_state_update(raw)
    if discard:
        visible, update = reply, None
    state = merge_state({}, update)
    state["turn_count"] = 0
    assistant_summary = summary_from_update(update, "assistant_response_summary", "初回の枠づけを提示した。")
    async with user_tx(uid) as conn:
        await conn.execute("update public.mi_sessions set state = %(state)s::jsonb where id = %(sid)s and user_id = %(uid)s", {"state": __import__('json').dumps(state, ensure_ascii=False), "sid": session["id"], "uid": uid})
        cur = await conn.execute("insert into public.mi_messages (session_id, user_id, role, content, is_verbatim, turn_index) values (%(sid)s, %(uid)s, 'assistant', %(content)s, %(verbatim)s, 0) returning id, role, content, is_verbatim, turn_index, created_at", {"sid": session["id"], "uid": uid, "content": visible if discard else assistant_summary, "verbatim": discard})
        message = await cur.fetchone()
    return {"session": session, "assistant_message": {**message, "content": visible}, "existing": False}


@router.post("/message")
async def post_message(body: MiMessageIn, uid: str = Depends(get_current_user), client: LLMClient | None = Depends(get_llm_client)):
    if client is None:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE)
    # 入力ゲートは必ず OR。detect_crisis_llm は既存の純粋サービスを流用する。
    try:
        crisis = detect_crisis_in_texts([body.content]) or await detect_crisis_llm(
            client, body.content, fail_closed=True
        )
    except Exception:  # noqa: BLE001 入力判定不能は fail closed
        crisis = True
    async with user_tx(uid) as conn:
        session = await _active(conn, uid)
        if not session:
            raise HTTPException(status_code=409, detail="有効なMIセッションがありません")
        if crisis:
            support = crisis_support_text()
            await conn.execute("update public.mi_sessions set status='halted', crisis_flag=true where id=%(sid)s and user_id=%(uid)s", {"sid": session["id"], "uid": uid})
            cur = await conn.execute("insert into public.mi_messages (session_id, user_id, role, content, is_verbatim, turn_index) values (%(sid)s, %(uid)s, 'assistant', %(content)s, true, %(turn)s) returning id, role, content, is_verbatim, turn_index, created_at", {"sid": session["id"], "uid": uid, "content": support, "turn": session["turn_count"] + 1})
            msg = await cur.fetchone()
            return {"assistant_message": msg, "crisis_notice": True, "boundary_suggested": False}
        cur = await conn.execute("select role, content from public.mi_messages where session_id=%(sid)s and user_id=%(uid)s order by turn_index desc, created_at desc limit %(lim)s", {"sid": session["id"], "uid": uid, "lim": _CONTEXT_LIMIT})
        history = list(reversed(await cur.fetchall()))
    state = dict(session["state"] or {})
    context = "\n".join(f"{m['role']}の要約: {m['content']}" for m in history)
    user_prompt = wrap_user_data(body.content, "クライアントの発話") + "\n直近要約履歴（参考データ）:\n" + wrap_user_data(context, "要約履歴")
    try:
        raw = await client.complete_text(system=build_mi_system_prompt({**state, "turn_count": session["turn_count"]}), user=user_prompt, max_tokens=500, model=settings.mi_model)
        discarded, safe_reply = await check_output(raw, state, client)
    except Exception:  # noqa: BLE001 応答/安全点検の障害は窓口案内で停止
        discarded, safe_reply = True, crisis_support_text()
    visible, update = extract_state_update(raw if not discarded else "")
    if discarded:
        visible, update = safe_reply, None
    next_turn = session["turn_count"] + 1
    next_state = merge_state(state, update)
    next_state["turn_count"] = next_turn
    user_summary = summary_from_update(update, "user_utterance_summary", "クライアントが発話した（要約の生成に失敗）。")
    assistant_summary = summary_from_update(update, "assistant_response_summary", "面接者が応答した（要約の生成に失敗）。")
    async with user_tx(uid) as conn:
        # 危険な出力はここで halted にして後続MIを防ぐ。
        await conn.execute("update public.mi_sessions set state=%(state)s::jsonb, turn_count=%(turn)s, status=case when %(halt)s then 'halted' else status end, crisis_flag=crisis_flag or %(halt)s where id=%(sid)s and user_id=%(uid)s", {"state": __import__('json').dumps(next_state, ensure_ascii=False), "turn": next_turn, "halt": discarded, "sid": session["id"], "uid": uid})
        await conn.execute("insert into public.mi_messages (session_id, user_id, role, content, is_verbatim, turn_index) values (%(sid)s, %(uid)s, 'user', %(content)s, false, %(turn)s)", {"sid": session["id"], "uid": uid, "content": user_summary, "turn": next_turn})
        cur = await conn.execute("insert into public.mi_messages (session_id, user_id, role, content, is_verbatim, turn_index) values (%(sid)s, %(uid)s, 'assistant', %(content)s, %(verbatim)s, %(turn)s) returning id, role, content, is_verbatim, turn_index, created_at", {"sid": session["id"], "uid": uid, "content": visible if discarded else assistant_summary, "verbatim": discarded, "turn": next_turn})
        msg = await cur.fetchone()
    return {"assistant_message": {**msg, "content": visible}, "crisis_notice": discarded, "boundary_suggested": boundary_suggested(next_turn)}


@router.post("/session/close")
async def close_session(uid: str = Depends(get_current_user), client: LLMClient | None = Depends(get_llm_client)):
    async with user_tx(uid) as conn:
        session = await _active(conn, uid)
        if not session:
            raise HTTPException(status_code=409, detail="有効なMIセッションがありません")
        cur = await conn.execute("select content from public.mi_messages where session_id=%(sid)s and user_id=%(uid)s order by turn_index, created_at", {"sid": session["id"], "uid": uid})
        summaries = await cur.fetchall()
    # 追加の生成は終了要約に限定。失敗時は保存済み要約を短く連結して閉じる。
    fallback = "セッションを終了しました。今回の対話の要点は、保存された要約からいつでも振り返れます。"
    summary = fallback
    if client is not None:
        try:
            summary = await client.complete_text(system="あなたはMIセッションの終了要約器です。診断や助言をせず、与えられた要約だけから短い日本語の要約を書いてください。", user=wrap_user_data("\n".join(row["content"] for row in summaries), "セッション要約"), max_tokens=250, model=settings.mi_model)
        except Exception:  # noqa: BLE001
            pass
    async with user_tx(uid) as conn:
        cur = await conn.execute("update public.mi_sessions set status='closed', last_summary=%(summary)s where id=%(sid)s and user_id=%(uid)s and status='active' returning *", {"summary": summary or fallback, "sid": session["id"], "uid": uid})
        closed = await cur.fetchone()
    return {"session": closed, "summary": closed["last_summary"]}
