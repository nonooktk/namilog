// スコア帯の判定と、評価語を避けた表示文言（デザイン仕様2.4 / 6.2）。
// 「良い/悪い」で語らず、色だけに依存させない（数値・ラベルを必ず併記）。

import type { ScoreBand } from "./types";

export function scoreBand(score: number): ScoreBand {
  if (score <= 3) return "low";
  if (score <= 6) return "mid";
  return "high";
}

/** スコアバッジ直下などに添える短いラベル（デザイン2.4）。 */
export function bandLabel(score: number): string {
  switch (scoreBand(score)) {
    case "low":
      return "ゆっくりめの日";
    case "mid":
      return "おだやかな日";
    case "high":
      return "動きやすい日";
  }
}

/** 本日の様子に添える寄り添い文言（デザイン6.2）。 */
export function todayMessage(score: number): string {
  switch (scoreBand(score)) {
    case "low":
      return "今日はゆっくりめの日みたい。無理しなくて大丈夫だよ";
    case "mid":
      return "今日はおだやかな一日みたいだね";
    case "high":
      return "今日は動きやすい日みたい。無理のない範囲で楽しんでね";
  }
}
