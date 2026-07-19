"use client";

// フィードバックチャット（NL-API-14: GET /api/feedback、NL-API-15: POST /api/feedback）。
// デザイン仕様5.6: 吹き出しUI（アプリ=左・Secondary Light / 本人=右・Primary Light、角丸18px しっぽなし）、
// 下部固定の入力欄＋送信ボタン。送信中は楽観表示（本人の吹き出しを即座に出す）。
// crisis_notice=true のとき相談窓口カードをやさしく表示する（デザイン5.7 / 6.5）。
// トーン: 責めない・寄り添う文言（デザイン6章）。

import { useEffect, useRef, useState } from "react";
import { namilogApi } from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { FeedbackMessage, PredictionNote } from "@/lib/types";
import { AppHeader } from "@/components/AppHeader";
import { SupportCard } from "@/components/SupportCard";
import { IwashiTaro, IWASHI } from "@/components/IwashiTaro";

const MAX_CHARS = 2000; // バックエンド FEEDBACK_MAX_CHARS と一致（超過は 422）。

// 楽観表示の仮メッセージには負の一時 id を振り、確定応答で置き換える。
let tempSeq = -1;

export default function FeedbackPage() {
  const [messages, setMessages] = useState<FeedbackMessage[]>([]);
  const [note, setNote] = useState<PredictionNote | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [crisis, setCrisis] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);

  // 初期ロード: 会話履歴（＋あれば今週のふりかえりメモ）を取得。
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const [fb, notes] = await Promise.all([
          namilogApi.getFeedback(null, 50),
          // ノートは任意情報。失敗しても会話は表示できるよう握りつぶす。
          namilogApi.getCurrentNote().catch(() => ({ note: null })),
        ]);
        if (!mounted) return;
        setMessages(fb.messages ?? []);
        setNote(notes.note ?? null);
      } catch {
        if (mounted) setLoadError("会話を読み込めませんでした。通信状況を確認してね。");
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  // メッセージ追加時に最下部へスクロール（新しい発話が見えるように）。
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, loading, crisis]);

  const trimmed = input.trim();
  const canSend = trimmed.length > 0 && trimmed.length <= MAX_CHARS && !sending;

  async function handleSend() {
    if (!canSend) return;
    const content = trimmed;
    setSendError(null);

    // 楽観表示: 本人の吹き出しを即座に描画し、入力欄をクリアする。
    const optimistic: FeedbackMessage = {
      id: String(tempSeq--),
      prediction_id: null,
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimistic]);
    setInput("");
    setSending(true);

    try {
      const res = await namilogApi.postFeedback(content, null);
      // 仮の吹き出しを確定版に差し替え、assistant 応答を追加する。
      setMessages((prev) => [
        ...prev.filter((m) => m.id !== optimistic.id),
        res.user_message,
        res.assistant_message,
      ]);
      if (res.crisis_notice) setCrisis(true);
    } catch (e) {
      // 失敗時は仮の吹き出しを取り消し、入力内容を戻して再送できるようにする。
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
      setInput(content);
      const msg =
        e instanceof ApiError && e.status === 422
          ? "メッセージを入力してから送ってね。"
          : "うまく送れませんでした。少し待って、もう一度試してね。";
      setSendError(msg);
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

  return (
    <>
      <AppHeader title="ふりかえり" back />
      <main className="screen screen--chat">
        <h1 className="screen-title">ふりかえり</h1>

        {/* イワシ太郎（1画面1箇所・控えめな一言）。危機案内表示中は静かな運用のため出さない
            （§11.4-2。承認済みの静かな文言が本画面に無いため非表示にする）。§11.3 */}
        {!crisis && <IwashiTaro message={IWASHI.feedback} variant="sub" />}

        <div className="chat-scroll" ref={scrollRef} role="log" aria-live="polite" aria-label="会話">
          {loading && <p className="empty-note">読み込み中…</p>}

          {loadError && (
            <p className="error-note" role="alert">
              {loadError}
            </p>
          )}

          {!loading && !loadError && (
            <>
              {note && (
                <div className="chat-note" role="note" aria-label="今週のふりかえりメモ">
                  <span className="tag">今週のふりかえりメモ</span>
                  <p>{note.content}</p>
                </div>
              )}

              {messages.length === 0 && !note && (
                <p className="empty-note">
                  昨日の予測、当たってたかな？感じたことを教えてくれると、次はもっと寄り添えるよ。
                </p>
              )}

              {messages.map((m) => (
                <div key={m.id} className={`msg-row${m.role === "user" ? " me" : ""}`}>
                  <div className={`bubble ${m.role === "user" ? "me" : "app"}`}>
                    <span className="sr-only">
                      {m.role === "user" ? "あなた: " : "なみログ: "}
                    </span>
                    {m.content}
                  </div>
                </div>
              ))}

              {crisis && <SupportCard />}
            </>
          )}
        </div>

        {sendError && (
          <p className="error-note" role="alert" style={{ marginBottom: 8 }}>
            {sendError}
          </p>
        )}

        <div className="chat-input-bar">
          <label htmlFor="chat-input" className="sr-only">
            メッセージ入力
          </label>
          <input
            id="chat-input"
            className="chat-input"
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            maxLength={MAX_CHARS}
            placeholder="感じたことを教えてね"
            disabled={loading}
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
      </main>
    </>
  );
}
