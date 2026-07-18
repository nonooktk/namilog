"use client";

// ログイン画面。Supabase Auth の Google ログイン（ARCHITECTURE.md §1.3）。
// 実 E2E は Google Client ID/Secret（統括手配）待ちのため動作未検証。
// すでにログイン済みならホームへ送る。OAuth リダイレクト後は detectSessionInUrl が
// セッションを拾い、onAuthStateChange 経由でホームへ遷移する。

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase, signInWithGoogle } from "@/lib/supabase";
import { warmUpApi } from "@/lib/warmup";
import { DisclaimerBar } from "@/components/DisclaimerBar";

export default function LoginPage() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    // ログイン画面表示と同時に API を起こしておく（Render Free のコールドスタート先行）。
    // fire-and-forget: 失敗は無視・ユーザーには見せない。
    warmUpApi();
    supabase.auth.getSession().then(({ data }) => {
      if (mounted && data.session) router.replace("/");
    });
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session) router.replace("/");
    });
    return () => {
      mounted = false;
      subscription.unsubscribe();
    };
  }, [router]);

  async function handleLogin() {
    setBusy(true);
    setError(null);
    try {
      const redirectTo =
        typeof window !== "undefined"
          ? `${window.location.origin}/`
          : undefined;
      const { error: signInError } = await signInWithGoogle(redirectTo);
      if (signInError) {
        setError("ログインを開始できませんでした。時間をおいてもう一度試してね。");
        setBusy(false);
      }
      // 成功時は Google へリダイレクトするため、ここには戻ってこない。
    } catch {
      setError("ログインを開始できませんでした。時間をおいてもう一度試してね。");
      setBusy(false);
    }
  }

  return (
    <div className="app-shell">
      <div className="login-hero">
        <div className="logo-mark" aria-hidden="true">
          🌊
        </div>
        <h1>なみログ</h1>
        <p>
          体調の波を、やさしく記録。
          <br />
          まずは Google でログインしてはじめよう。
        </p>
      </div>

      <main className="screen">
        {error && (
          <p className="error-note" role="alert">
            {error}
          </p>
        )}
        <button
          className="google-btn"
          onClick={handleLogin}
          disabled={busy}
          aria-label="Googleアカウントでログイン"
        >
          <span aria-hidden="true">🔵</span>
          {busy ? "ログイン中…" : "Googleアカウントでログイン"}
        </button>
        <p className="field-hint" style={{ marginTop: 12, textAlign: "center" }}>
          はじめての方も、このボタンからはじめられるよ。
        </p>
      </main>

      <DisclaimerBar />
    </div>
  );
}
