import type { Metadata, Viewport } from "next";
import { M_PLUS_Rounded_1c } from "next/font/google";
import "./globals.css";
import { ServiceWorkerRegister } from "@/components/ServiceWorkerRegister";

// デザイン仕様3.1: 丸ゴシック系「M PLUS Rounded 1c」を next/font でセルフホスト。
// 日本語フォントは全ウェイト preload するとサイズが大きいため preload:false とし、
// display:swap でフォールバック（丸ゴシックスタック）から差し替える。
const mplus = M_PLUS_Rounded_1c({
  weight: ["400", "700"],
  subsets: ["latin"],
  display: "swap",
  preload: false,
  variable: "--font-mplus",
  fallback: [
    "BIZ UDPGothic",
    "Hiragino Maru Gothic ProN",
    "Yu Gothic Medium",
    "Hiragino Sans",
    "sans-serif",
  ],
});

export const metadata: Metadata = {
  title: "なみログ",
  description: "体調の波を客観指標で予測し、やさしく注意喚起する体調記録アプリ。",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#FFFBF6",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja" className={mplus.variable}>
      <body>
        {/* 本番のみ SW を登録（保守的キャッシュ）。開発時は既存 SW を掃除する。 */}
        <ServiceWorkerRegister />
        {children}
      </body>
    </html>
  );
}
