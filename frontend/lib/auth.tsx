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
    } = supabase.auth.onAuthStateChange((_event, s) => {
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

function FullScreenLoading() {
  return (
    <div className="center-fill" role="status" aria-live="polite">
      <div className="spinner" aria-hidden="true" />
      <span>読み込み中…</span>
    </div>
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
    return <FullScreenLoading />;
  }
  return <>{children}</>;
}
