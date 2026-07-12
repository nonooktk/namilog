/*
 * なみログ Service Worker（保守的キャッシュ）
 * 正本方針: 01_ナレッジ/Web/service-worker-conservative-caching.md / ARCHITECTURE.md §6.1
 *
 * 原則「攻めない・壊さない」:
 *  - 別オリジン（Supabase Auth の OAuth/iframe 等）は早期 return で完全非介入。
 *  - /api/ 等の動的データは一切キャッシュしない（ネットワーク直行）。
 *  - HTML は network-first・保存しない。オフライン時のみ簡易フォールバック。
 *  - /_next/static/（content-hash 付き）のみ cache-first（status 200 のときだけ保存）。
 *  - キャッシュ名をバージョニングし activate で旧キャッシュを削除。
 *  - skipWaiting + clients.claim で即時反映（content-hash 静的資産のみ保存のため旧タブ影響は低い）。
 */

// キャッシュ名バージョニング。SW を変更したら必ず番号を上げる（activate で旧版を削除）。
const CACHE_NAME = "namilog-static-v1";

// オフライン時に navigate へ返す簡易フォールバック（保存はこのページのみ）。
const OFFLINE_URL = "/offline.html";

self.addEventListener("install", (event) => {
  // オフラインフォールバックだけ事前キャッシュ。ほかは動的に扱う（積極的プリキャッシュはしない）。
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.add(OFFLINE_URL))
      .catch(() => {
        // フォールバックが取得できなくても SW 自体は生かす（壊さない優先）。
      })
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;

  // GET 以外（POST 等）は介入しない。
  if (req.method !== "GET") return;

  let url;
  try {
    url = new URL(req.url);
  } catch {
    return;
  }

  // 別オリジン（認証 iframe / Supabase / API ドメイン等）は完全非介入。
  // これを守らないと Google/Supabase の認証フローを壊す（最重要）。
  if (url.origin !== self.location.origin) return;

  // /api/ 等の動的データはネットワーク直行、キャッシュしない。
  if (url.pathname.startsWith("/api/")) return;

  // content-hash 付き静的アセットのみ cache-first。
  if (url.pathname.startsWith("/_next/static/")) {
    event.respondWith(cacheFirst(req));
    return;
  }

  // HTML（ページ遷移）は network-first・無保存。オフライン時のみフォールバック。
  if (req.mode === "navigate") {
    event.respondWith(networkFirstNoStore(req));
    return;
  }
  // それ以外（画像・font 等の同一オリジン）はブラウザ既定に委ねる（介入しない）。
});

async function cacheFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);
  if (cached) return cached;
  const res = await fetch(request);
  // opaque 応答やエラー応答をキャッシュしない（200 のときだけ保存）。
  if (res && res.status === 200) {
    cache.put(request, res.clone());
  }
  return res;
}

async function networkFirstNoStore(request) {
  try {
    // 成功時も保存しない（常に最新の HTML を取りにいく）。
    return await fetch(request);
  } catch {
    const cache = await caches.open(CACHE_NAME);
    const fallback = await cache.match(OFFLINE_URL);
    if (fallback) return fallback;
    // フォールバックも無ければ簡素な応答を返す（真っ白よりまし）。
    return new Response(
      "<!doctype html><meta charset='utf-8'><title>オフライン</title>" +
        "<body style='font-family:sans-serif;padding:24px;color:#4A4458'>" +
        "<h1>オフラインです</h1><p>通信が回復したら、もう一度お試しください。</p></body>",
      { headers: { "Content-Type": "text/html; charset=utf-8" }, status: 503 },
    );
  }
}
