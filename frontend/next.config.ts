import type { NextConfig } from "next";

// SW と manifest 自体のキャッシュ制御（保守的キャッシュ方針: 01_ナレッジ/Web/service-worker-conservative-caching.md）。
// /sw.js と /manifest.webmanifest が長寿命キャッシュされると SW 更新が最大24時間遅延しうるため、
// 常にネットワーク検証させる（no-cache）。standalone 出力でも有効（output:"export" のときのみ無効）。
const NO_STORE = "no-cache, max-age=0, must-revalidate";

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        source: "/sw.js",
        headers: [{ key: "Cache-Control", value: NO_STORE }],
      },
      {
        // app/manifest.ts が配信する Web App Manifest。
        source: "/manifest.webmanifest",
        headers: [{ key: "Cache-Control", value: NO_STORE }],
      },
    ];
  },
};

export default nextConfig;
