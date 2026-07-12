import type { MetadataRoute } from "next";

// Web App Manifest（ARCHITECTURE.md §6.1 / デザイン仕様2.2）。
// App Router では app/manifest.ts を置くと /manifest.webmanifest が配信され、
// <link rel="manifest"> が自動注入される（SW 保守的キャッシュナレッジ）。
// theme/background はデザイン仕様のベース色。アイコンはローカル生成（外部サービス不使用）。
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    lang: "ja",
    dir: "ltr",
    name: "なみログ",
    short_name: "なみログ",
    description:
      "体調の波を客観指標で予測し、やさしく注意喚起する体調記録アプリ。",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    // デザイン仕様2.1 背景（Base）/ 2.2 Primary（ラベンダー）。
    background_color: "#FFFBF6",
    theme_color: "#A78BC9",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      {
        src: "/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
