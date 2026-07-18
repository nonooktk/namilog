"use client";

// 認証を要する画面（ホーム・体調入力・詳細履歴・外部情報選択）の共通レイアウト。
// - AuthProvider でセッションを購読し、RequireAuth で未ログインを /login へ送る。
// - OnboardingGate: 未オンボーディング（profiles.onboarded_at == null）なら /onboarding へ送る。
//   判定失敗時はホームを塞がない（degrade）。/login と /onboarding は別ルートグループのため対象外。
// - 医療免責バーを全画面のフッターに常設する（デザイン仕様5.7）。
// ルートグループ (app) は URL に現れないため、(app)/page.tsx が "/"（ホーム）になる。

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AuthProvider, RequireAuth, useAuth } from "@/lib/auth";
import { DisclaimerBar } from "@/components/DisclaimerBar";
import { GentleLoader } from "@/components/GentleLoader";
import { namilogApi } from "@/lib/api";
import { prefetchHome, clearPrefetchedHome } from "@/lib/prefetch";
import type { Profile } from "@/lib/types";

/**
 * オンボーディング未完了なら /onboarding へ誘導するゲート。
 * - getProfile 成功かつ onboarded_at が未設定なら /onboarding へ。
 * - 取得失敗・profile 不明のときはホームを塞がず通す（degrade）。ここで詰まらせない。
 * RequireAuth の内側に置くのでセッションは確定している前提。
 */
function OnboardingGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  // RequireAuth の内側なのでセッションは確定済み。先行取得の紐付けに userId を使う。
  const { session } = useAuth();
  const userId = session?.user.id ?? null;
  // "checking": 判定中 / "pass": 通す / "redirect": /onboarding へ送る途中。
  const [phase, setPhase] = useState<"checking" | "pass" | "redirect">(
    "checking",
  );

  useEffect(() => {
    let mounted = true;
    // ホーム取得を profile 取得と並列に先行起動して総待ち時間を縮める。
    // 現セッションの userId に紐付ける（セッション跨ぎの再利用を防ぐ）。
    // /onboarding へ送ると確定した場合は破棄する（この取得は degrade 前提の保険）。
    if (userId) prefetchHome(userId);
    (async () => {
      try {
        const profile = (await namilogApi.getProfile()) as Profile | null;
        if (!mounted) return;
        if (profile && profile.onboarded_at == null) {
          clearPrefetchedHome();
          setPhase("redirect");
          router.replace("/onboarding");
        } else {
          setPhase("pass");
        }
      } catch {
        // 判定失敗時はホームを塞がない（degrade）。先行取得はホームでそのまま消費する。
        if (mounted) setPhase("pass");
      }
    })();
    return () => {
      mounted = false;
    };
  }, [router, userId]);

  if (phase !== "pass") {
    return <GentleLoader />;
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
