"use client";

// 認証を要する画面（ホーム・体調入力・詳細履歴・外部情報選択）の共通レイアウト。
// - AuthProvider でセッションを購読し、RequireAuth で未ログインを /login へ送る。
// - OnboardingGate: 未オンボーディング（profiles.onboarded_at == null）なら /onboarding へ送る。
//   判定失敗時はホームを塞がない（degrade）。/login と /onboarding は別ルートグループのため対象外。
// - 医療免責バーを全画面のフッターに常設する（デザイン仕様5.7）。
// ルートグループ (app) は URL に現れないため、(app)/page.tsx が "/"（ホーム）になる。

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AuthProvider, RequireAuth } from "@/lib/auth";
import { DisclaimerBar } from "@/components/DisclaimerBar";
import { namilogApi } from "@/lib/api";
import type { Profile } from "@/lib/types";

function GateLoading() {
  return (
    <div className="center-fill" role="status" aria-live="polite">
      <div className="spinner" aria-hidden="true" />
      <span>読み込み中…</span>
    </div>
  );
}

/**
 * オンボーディング未完了なら /onboarding へ誘導するゲート。
 * - getProfile 成功かつ onboarded_at が未設定なら /onboarding へ。
 * - 取得失敗・profile 不明のときはホームを塞がず通す（degrade）。ここで詰まらせない。
 * RequireAuth の内側に置くのでセッションは確定している前提。
 */
function OnboardingGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  // "checking": 判定中 / "pass": 通す / "redirect": /onboarding へ送る途中。
  const [phase, setPhase] = useState<"checking" | "pass" | "redirect">(
    "checking",
  );

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const profile = (await namilogApi.getProfile()) as Profile | null;
        if (!mounted) return;
        if (profile && profile.onboarded_at == null) {
          setPhase("redirect");
          router.replace("/onboarding");
        } else {
          setPhase("pass");
        }
      } catch {
        // 判定失敗時はホームを塞がない（degrade）。
        if (mounted) setPhase("pass");
      }
    })();
    return () => {
      mounted = false;
    };
  }, [router]);

  if (phase !== "pass") {
    return <GateLoading />;
  }
  return <>{children}</>;
}

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthProvider>
      <RequireAuth>
        <OnboardingGate>
          <div className="app-shell">
            {children}
            <DisclaimerBar />
          </div>
        </OnboardingGate>
      </RequireAuth>
    </AuthProvider>
  );
}
