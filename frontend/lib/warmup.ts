// Render Free のコールドスタート対策（ログイン後ヨミコミ タンシュク）。
//
// ログイン画面の表示時に /health を1回だけ叩き、スリープ中の API を先行して起こす。
// fire-and-forget: 成否・遅延はユーザーに一切見せない。リトライもしない（起床のトリガーが目的）。
// バックエンドの /health は認証不要の疎通確認エンドポイント（backend/app/main.py）。

import { API_BASE } from "./api";

/**
 * API のウォームアップ ping を1回だけ送る。
 * 例外は握りつぶし、呼び出し元に影響を与えない（副作用のみ・戻り値なし）。
 */
export function warmUpApi(): void {
  try {
    // keepalive: ログイン→リダイレクトで画面が離れても送信を完了させる。
    // cache: no-store で中間キャッシュを避け、確実にサーバへ到達させる。
    void fetch(`${API_BASE}/health`, {
      method: "GET",
      credentials: "omit",
      cache: "no-store",
      keepalive: true,
    }).catch(() => {
      // 失敗は無視。起床のきっかけを与えるだけでよい。
    });
  } catch {
    // fetch 呼び出し自体が同期的に投げても無視する。
  }
}
