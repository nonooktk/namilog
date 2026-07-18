"use client";

// やさしいトーンのローディング表示（待ち体験の改善）。
// 通常は「読み込み中…」を出し、長引く（既定 5 秒超）ときだけコールドスタートを
// 案内する文言に切り替える。Render Free の起床待ちを不安にさせないための配慮。

import { useEffect, useState } from "react";

/**
 * マウントから delayMs 経過後に true になるフラグ。ローディングが長引いたときの
 * 表示切り替えに使う。アンマウント時にタイマーを片付ける。
 */
export function useDelayedFlag(delayMs: number): boolean {
  const [flag, setFlag] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setFlag(true), delayMs);
    return () => clearTimeout(timer);
  }, [delayMs]);
  return flag;
}

/**
 * 全画面のローディング。長引いたら文言をやわらかい起床メッセージに差し替える。
 */
export function GentleLoader({
  delayMs = 5000,
  base = "読み込み中…",
  waking = "サーバーをそっと起こしています…",
}: {
  delayMs?: number;
  base?: string;
  waking?: string;
}) {
  const slow = useDelayedFlag(delayMs);
  return (
    <div className="center-fill" role="status" aria-live="polite">
      <div className="spinner" aria-hidden="true" />
      <span>{slow ? waking : base}</span>
    </div>
  );
}
