"use client";

// こころの整理（MI セッション）。設計書「MIセッション設計」§3 準拠。
// FB チャット（/feedback）とは別実装・別エンドポイント（/api/mi/*）。CSS クラスのみ流用する。
// 安全第一（設計 §6）:
//  - 冒頭で「治療・診断ではない／専門支援の代替でない／記録は要約のみ」を明示（枠づけ）。
//  - 危機検知（crisis_notice / status=halted）時は SupportCard を表示し、入力をやさしく閉じる。
//    自動でセッションへ戻さない（再開導線を出さない）。
//  - セッション境界（boundary_suggested=true）で [もう少し続ける][今日はここまで] を提示。
//    終了後は新セッション開始導線を出す（無制限チャットにしない）。

import { useEffect, useRef, useState } from "react";
import { namilogApi, ApiError } from "@/lib/api";
import type { MiMessage } from "@/lib/types";
import { AppHeader } from "@/components/AppHeader";
import { SupportCard } from "@/components/SupportCard";

const MAX_CHARS = 2000; // バックエンド MI_MAX_CHARS と一致（超過は 422）。
const BOUNDARY_TURN = 15; // バックエンド mi_session.BOUNDARY_TURN と一致。

// 画面フェーズ。intro=未開始 / chatting=対話中 / closed=区切り済み。
type Phase = "loading" | "intro" | "chatting" | "closed";

// 楽観表示の仮メッセージには負の一時 id を振る。
let tempSeq = -1;

const UNAVAILABLE = "この対話はいまお休み中です。時間をおいて、もう一度試してね。";

export default function MiPage() {
  const [phase, setPhase] = useState<Phase>("loading");
  const [messages, setMessages] = useState<MiMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [starting, setStarting] = useState(false);
  const [closing, setClosing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [crisis, setCrisis] = useState(false);
  const [boundary, setBoundary] = useState(false);
  const [closingSummary, setClosingSummary] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);

  // 初期ロード: 進行中セッションと直近メッセージ（要約列）を取得。
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const res = await namilogApi.getMiSession(50);
        if (!mounted) return;
        if (res.session) {
          setMessages(res.messages ?? []);
          setBoundary(res.session.turn_count >= BOUNDARY_TURN);
          setPhase("chatting");
        } else {
          setPhase("intro");
        }
      } catch {
        if (mounted) {
          setLoadError("会話を読み込めませんでした。通信状況を確認してね。");
          setPhase("intro");
        }
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  // メッセージ追加・状態変化で最下部へスクロール。
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, phase, crisis, boundary]);

  // ---- セッション開始（intro / closed から） ----
  async function handleStart() {
    if (starting) return;
    setStarting(true);
    setLoadError(null);
    setSendError(null);
    setClosingSummary(null);
    setCrisis(false);
    setBoundary(false);
    try {
      const res = await namilogApi.startMiSession(null);
      if (res.existing) {
        // 既存 active があれば冪等開始。メッセージを取り直す。
        const cur = await namilogApi.getMiSession(50);
        setMessages(cur.messages ?? []);
        setBoundary((cur.session?.turn_count ?? 0) >= BOUNDARY_TURN);
      } else {
        setMessages(res.assistant_message ? [res.assistant_message] : []);
      }
      setPhase("chatting");
    } catch (e) {
      setLoadError(
        e instanceof ApiError && e.status === 503
          ? UNAVAILABLE
          : "はじめられませんでした。少し待って、もう一度試してね。",
      );
    } finally {
      setStarting(false);
    }
  }

  const trimmed = input.trim();
  const canSend =
    trimmed.length > 0 && trimmed.length <= MAX_CHARS && !sending && !crisis;

  // ---- 発話送信 ----
  async function handleSend() {
    if (!canSend) return;
    const content = trimmed;
    setSendError(null);

    // 楽観表示: 本人の発話をそのまま吹き出しに出す（DB には要約が保存される）。
    const optimistic: MiMessage = {
      id: String(tempSeq--),
      role: "user",
      content,
      is_verbatim: false,
      turn_index: (messages[messages.length - 1]?.turn_index ?? 0) + 1,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimistic]);
    setInput("");
    setSending(true);

    try {
      const res = await namilogApi.postMiMessage(content);
      // 本人の発話（入力どおり）を残しつつ、面接者応答を追加する。
      setMessages((prev) => [
        ...prev.filter((m) => m.id !== optimistic.id),
        optimistic,
        res.assistant_message,
      ]);
      if (res.crisis_notice) setCrisis(true);
      setBoundary(res.boundary_suggested);
    } catch (e) {
      // 失敗時は仮の吹き出しを取り消し、入力を戻して再送できるようにする。
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
      setInput(content);
      if (e instanceof ApiError && e.status === 409) {
        // セッションが無効（区切り済み/中断）。開始導線へ戻す。
        setPhase("intro");
        setLoadError("セッションが見つかりませんでした。新しくはじめてね。");
      } else if (e instanceof ApiError && e.status === 422) {
        setSendError("メッセージを入力してから送ってね。");
      } else if (e instanceof ApiError && e.status === 503) {
        setSendError(UNAVAILABLE);
      } else {
        setSendError("うまく送れませんでした。少し待って、もう一度試してね。");
      }
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    // Enter で送信（IME 変換確定中は送らない）。
    if (e.key === "Enter" && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSend();
    }
  }

  // ---- 区切り: もう少し続ける ----
  function handleContinue() {
    setBoundary(false);
  }

  // ---- 区切り: 今日はここまで（セッションを閉じる） ----
  async function handleClose() {
    if (closing) return;
    setClosing(true);
    setSendError(null);
    try {
      const res = await namilogApi.closeMiSession();
      setClosingSummary(res.summary);
      setBoundary(false);
      setPhase("closed");
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        // すでに区切り済み。終了画面へ寄せる。
        setBoundary(false);
        setPhase("closed");
      } else {
        setSendError("うまく閉じられませんでした。もう一度試してね。");
      }
    } finally {
      setClosing(false);
    }
  }

  return (
    <>
      <AppHeader title="こころの整理" back />
      <main className="screen screen--chat">
        <h1 className="screen-title">こころの整理</h1>

        <div
          className="chat-scroll"
          ref={scrollRef}
          role="log"
          aria-live="polite"
          aria-label="会話"
        >
          {phase === "loading" && <p className="empty-note">読み込み中…</p>}

          {loadError && (
            <p className="error-note" role="alert">
              {loadError}
            </p>
          )}

          {phase === "intro" && (
            <div className="mi-panel">
              <div className="chat-note" role="note" aria-label="こころの整理について">
                <span className="tag">こころの整理とは</span>
                <p>
                  変えたいこと・迷っていることを、いっしょに少しずつ整理していく対話です。
                  これは治療や診断ではなく、専門的な支援の代わりにはなりません。
                  記録は要約だけを残します。あなたのペースで大丈夫。
                </p>
              </div>
              <button
                type="button"
                className="btn btn-primary btn-block"
                onClick={handleStart}
                disabled={starting}
              >
                {starting ? "はじめています…" : "はじめる"}
              </button>
            </div>
          )}

          {(phase === "chatting" || phase === "closed") && (
            <>
              {/* 枠づけ（免責）: 対話中は冒頭に常設し、治療・診断でない旨を明示する（設計 §6.4）。 */}
              <div className="chat-note" role="note" aria-label="この対話について">
                <span className="tag">この対話について</span>
                <p>
                  これは治療や診断ではなく、考えや気持ちを整理するための対話です。
                  専門的な支援の代わりにはなりません。記録は要約だけを残します。
                </p>
              </div>

              {messages.map((m) => (
                <div
                  key={m.id}
                  className={`msg-row${m.role === "user" ? " me" : ""}`}
                >
                  <div className={`bubble ${m.role === "user" ? "me" : "app"}`}>
                    <span className="sr-only">
                      {m.role === "user" ? "あなた: " : "面接者: "}
                    </span>
                    {m.content}
                  </div>
                </div>
              ))}

              {/* 危機検知時: 窓口カードを表示し、以降の入力を抑制する（設計 §6.2）。 */}
              {crisis && <SupportCard />}

              {/* セッション境界の提案（危機時・終了後は出さない）。 */}
              {boundary && !crisis && phase === "chatting" && (
                <div className="chat-note" role="note" aria-label="区切りの提案">
                  <span className="tag">ひと区切り</span>
                  <p>
                    ここまでお話しできてよかった。今日はここで一区切りにしますか？
                    それとも、もう少し続けますか？
                  </p>
                  <div className="chat-actions">
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={handleContinue}
                      disabled={closing}
                    >
                      もう少し続ける
                    </button>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={handleClose}
                      disabled={closing}
                    >
                      {closing ? "閉じています…" : "今日はここまで"}
                    </button>
                  </div>
                </div>
              )}

              {/* 終了後: まとめと新セッション開始導線。 */}
              {phase === "closed" && (
                <div className="mi-panel">
                  <div className="chat-note" role="note" aria-label="今回のまとめ">
                    <span className="tag">今回のまとめ</span>
                    <p>
                      {closingSummary ??
                        "セッションを終了しました。おつかれさまでした。"}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="btn btn-primary btn-block"
                    onClick={handleStart}
                    disabled={starting}
                  >
                    {starting ? "はじめています…" : "新しく話をはじめる"}
                  </button>
                </div>
              )}
            </>
          )}
        </div>

        {sendError && (
          <p className="error-note" role="alert" style={{ marginBottom: 8 }}>
            {sendError}
          </p>
        )}

        {/* 入力欄は対話中かつ非危機時のみ。危機時は入力をやさしく閉じる。 */}
        {phase === "chatting" && !crisis && (
          <div className="chat-input-bar">
            <label htmlFor="mi-input" className="sr-only">
              メッセージ入力
            </label>
            <input
              id="mi-input"
              className="chat-input"
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              maxLength={MAX_CHARS}
              placeholder="いま思っていることを、そのまま書いてね"
              disabled={sending}
              aria-label="メッセージ入力"
            />
            <button
              type="button"
              className="send-btn"
              onClick={handleSend}
              disabled={!canSend}
              aria-label="送信"
            >
              <span aria-hidden="true">➤</span>
            </button>
          </div>
        )}

        {crisis && (
          <p className="disclaimer-bar" role="note" style={{ margin: "0 0 8px" }}>
            今日はここで対話をお休みします。上の窓口は、いつでも使ってね。
          </p>
        )}
      </main>
    </>
  );
}
