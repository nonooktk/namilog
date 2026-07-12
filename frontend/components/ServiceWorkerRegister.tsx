"use client";

// Service Worker 登録（ARCHITECTURE.md §6.1）。
// - 本番のみ登録する（開発時は未登録。開発中に古いキャッシュで悩まないため）。
// - 開発時に過去へ登録された SW が残っていたら unregister して掃除する。
// - 別オリジン非介入など保守的方針は public/sw.js 側で担保。

import { useEffect } from "react";

export function ServiceWorkerRegister() {
  useEffect(() => {
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) {
      return;
    }

    if (process.env.NODE_ENV === "production") {
      // updateViaCache:'none' で sw.js 自体は毎回ネットワーク検証（更新遅延を避ける）。
      navigator.serviceWorker
        .register("/sw.js", { scope: "/", updateViaCache: "none" })
        .catch(() => {
          // 登録失敗してもアプリは通常どおり動く（PWA は付加価値のため握りつぶす）。
        });
    } else {
      // 開発時: 既存 SW を掃除して、キャッシュ由来の不可解な挙動を防ぐ。
      navigator.serviceWorker.getRegistrations().then((regs) => {
        regs.forEach((r) => r.unregister());
      });
    }
  }, []);

  return null;
}
