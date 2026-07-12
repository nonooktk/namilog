"use client";

// オンボーディング画面の共通レイアウト（認証ガードのみ）。
// - (app) レイアウトとは別のルートグループにすることで、OnboardingGate（onboarded_at 判定→
//   /onboarding へ送る）の対象外になる。ここに Gate を置くと無限ループになるため置かない。
// - オンボーディングも本人の profiles を更新するため、未ログインは /login へ送る。
// - 免責バーはオンボーディング最終ステップ内で表示するため、フッター常設はしない。

import { AuthProvider, RequireAuth } from "@/lib/auth";

export default function OnboardingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthProvider>
      <RequireAuth>
        <div className="app-shell">{children}</div>
      </RequireAuth>
    </AuthProvider>
  );
}
