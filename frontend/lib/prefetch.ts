// ホーム取得の先行実行（getProfile との並列化）。
//
// ログイン後の初期化は OnboardingGate の getProfile → ホームの getHome が直列になり、
// コールドスタート復帰待ちと重なると体感が長い。そこで OnboardingGate 開始時に
// getHome を先行起動し、profile 取得と並列で走らせて総待ち時間を短縮する。
//
// ゲートの意味（未完了→/onboarding、判定失敗→degrade）は一切変えない。
// onboarding へ遷移する場合は先行取得を破棄し、古い結果が残らないようにする。

import { namilogApi } from "./api";
import type { HomeResponse } from "./types";

// 先行取得の有効期限。これを超えたキャッシュは使わず新規取得する（陳腐化の保険）。
const TTL_MS = 30_000;

let cached: { promise: Promise<HomeResponse>; at: number } | null = null;

/**
 * ホームデータの先行取得を開始する（重複起動はしない・副作用のみ）。
 * ここでの reject は消費側（consumeHome）で改めて処理する。
 */
export function prefetchHome(): void {
  if (cached) return;
  const promise = namilogApi.getHome() as Promise<HomeResponse>;
  // 消費されるまでの間に reject しても未処理拒否にならないよう握っておく。
  promise.catch(() => {});
  cached = { promise, at: Date.now() };
}

/**
 * 先行取得の結果を消費する。TTL 内の先行取得があればそれを、なければ新規取得を返す。
 * 一度きり（消費でキャッシュを解放）。次回のホーム表示では新しく取得される。
 */
export function consumeHome(): Promise<HomeResponse> {
  const fresh =
    cached && Date.now() - cached.at < TTL_MS ? cached.promise : null;
  cached = null;
  return fresh ?? (namilogApi.getHome() as Promise<HomeResponse>);
}

/**
 * 先行取得を破棄する。ホームを表示しないと確定したとき（/onboarding へ遷移する等）に呼ぶ。
 */
export function clearPrefetchedHome(): void {
  cached = null;
}
