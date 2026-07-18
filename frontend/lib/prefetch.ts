// ホーム取得の先行実行（getProfile との並列化）。
//
// ログイン後の初期化は OnboardingGate の getProfile → ホームの getHome が直列になり、
// コールドスタート復帰待ちと重なると体感が長い。そこで OnboardingGate 開始時に
// getHome を先行起動し、profile 取得と並列で走らせて総待ち時間を短縮する。
//
// ゲートの意味（未完了→/onboarding、判定失敗→degrade）は一切変えない。
//
// セッション分離: キャッシュは userId に紐付ける。consumeHome は現セッションの
// userId と一致する場合のみ再利用し、ログアウト（clearPrefetchedHome）や
// ユーザー切替では前ユーザーの取得結果を絶対に持ち越さない（セッション跨ぎの
// データ漏洩防止）。onboarding へ遷移する場合も破棄する。

import { namilogApi } from "./api";
import type { HomeResponse } from "./types";

// 先行取得の有効期限。これを超えたキャッシュは使わず新規取得する（陳腐化の保険）。
const TTL_MS = 30_000;

type CacheEntry = {
  userId: string;
  promise: Promise<HomeResponse>;
  at: number;
};

let cached: CacheEntry | null = null;

/** キャッシュが有効期限内かどうか。 */
function isFresh(entry: CacheEntry): boolean {
  return Date.now() - entry.at < TTL_MS;
}

/**
 * ホームデータの先行取得を開始する（副作用のみ）。
 * - userId: 取得を紐付ける現セッションのユーザーID。
 * - 期限切れ・別ユーザーの残骸が残っていれば破棄してから起動する。
 * - 同一ユーザーの有効なキャッシュがあれば重複起動しない。
 * ここでの reject は消費側（consumeHome）で改めて処理する。
 */
export function prefetchHome(userId: string): void {
  // 期限切れ、または別ユーザーのキャッシュは使い回さず捨てる。
  if (cached && (!isFresh(cached) || cached.userId !== userId)) {
    cached = null;
  }
  if (cached) return;
  const promise = namilogApi.getHome() as Promise<HomeResponse>;
  // 消費されるまでの間に reject しても未処理拒否にならないよう握っておく。
  promise.catch(() => {});
  cached = { userId, promise, at: Date.now() };
}

/**
 * 先行取得の結果を消費する。
 * - 現セッションの userId と一致し、かつ TTL 内の先行取得があればそれを返す。
 * - ユーザー不一致・期限切れ・先行取得なしのときは新規取得する（安全側）。
 * 一度きり（消費でキャッシュを解放）。次回のホーム表示では新しく取得される。
 */
export function consumeHome(userId: string): Promise<HomeResponse> {
  const usable =
    cached && cached.userId === userId && isFresh(cached)
      ? cached.promise
      : null;
  cached = null;
  return usable ?? (namilogApi.getHome() as Promise<HomeResponse>);
}

/**
 * 先行取得を破棄する。ホームを表示しないと確定したとき（/onboarding へ遷移）や、
 * ログアウト・セッション失効時（認証状態変更の導線）に呼ぶ。
 */
export function clearPrefetchedHome(): void {
  cached = null;
}
