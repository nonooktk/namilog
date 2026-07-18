"use client";

// 認証状態の共有（ARCHITECTURE.md §1.3）。
// Supabase セッションはブラウザにのみ存在するため、認証を要する画面はすべて Client Component。
// ここではセッションの購読と、未ログイン時の /login リダイレクトを担う。
// DB 直読みはしない（P-1）。取得した JWT は lib/api.ts が Authorization に付与する。

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "./supabase";
import { clearPrefetchedHome } from "./prefetch";
import { GentleLoader } from "@/components/GentleLoader";

interface AuthState {
  session: Session | null;
  loading: boolean;
}

const AuthContext = createContext<AuthState>({ session: null, loading: true });

export function useAuth(): AuthState {
  return useContext(AuthContext);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    supabase.auth.getSession().then(({ data }) => {
      if (!mounted) return;
      setSession(data.session);
      setLoading(false);
    });
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, s) => {
      // ログアウト時は未消費のホーム先行取得を破棄し、次にログインするユーザーへ
      // 前ユーザーのデータを持ち越さない（セッション跨ぎのデータ分離）。
      if (event === "SIGNED_OUT") clearPrefetchedHome();
      setSession(s);
      setLoading(false);
    });
    return () => {
      mounted = false;
      subscription.unsubscribe();
    };
  }, []);

  return (
    <AuthContext.Provider value={{ session, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

/** 未ログインなら /login へ送る。ログイン確定までローディングを表示する。 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !session) {
      router.replace("/login");
    }
  }, [loading, session, router]);

  if (loading || !session) {
    // 長引くとき（コールドスタート）はやさしい起床メッセージに切り替わる。
    return <GentleLoader />;
  }
  return <>{children}</>;
}
