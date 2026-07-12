// Supabase Auth（Google プロバイダ）クライアントの骨組み（ARCHITECTURE.md §1.3 / §8.1）。
//
// 責務は「認証のみ」。DB の直読み書きはしない（P-1: データアクセスは FastAPI 経由に一本化）。
// ここで取得した access_token(JWT) を lib/api.ts が Authorization ヘッダに付与して FastAPI を呼ぶ。
//
// M2 では骨組みまで。画面実装（ログイン導線・セッション監視）はイーブイが後続で担当する。

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!url || !anonKey) {
  // 環境変数未設定時は明示的に気づけるようにする（frontend/.env を参照）。
  // ビルドを止めないよう throw はしないが、開発中に検知できるよう警告する。
  // eslint-disable-next-line no-console
  console.warn(
    "[supabase] NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY が未設定です",
  );
}

// フロントでは anon 鍵のみ使用する。service_role 鍵は絶対に持ち込まない（§7.2）。
export const supabase: SupabaseClient = createClient(url ?? "", anonKey ?? "", {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
});

/** 現在のセッションの access_token(JWT) を返す。未ログインなら null。 */
export async function getAccessToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

/** Google ログインを開始する（OAuth リダイレクト）。画面実装で導線に接続する。 */
export async function signInWithGoogle(redirectTo?: string) {
  return supabase.auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo },
  });
}

export async function signOut() {
  return supabase.auth.signOut();
}
