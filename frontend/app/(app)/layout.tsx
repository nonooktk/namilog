"use client";

// 認証を要する画面（ホーム・体調入力・詳細履歴・外部情報選択）の共通レイアウト。
// - AuthProvider でセッションを購読し、RequireAuth で未ログインを /login へ送る。
// - 医療免責バーを全画面のフッターに常設する（デザイン仕様5.7）。
// ルートグループ (app) は URL に現れないため、(app)/page.tsx が "/"（ホーム）になる。

import { AuthProvider, RequireAuth } from "@/lib/auth";
import { DisclaimerBar } from "@/components/DisclaimerBar";

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthProvider>
      <RequireAuth>
        <div className="app-shell">
          {children}
          <DisclaimerBar />
        </div>
      </RequireAuth>
    </AuthProvider>
  );
}
