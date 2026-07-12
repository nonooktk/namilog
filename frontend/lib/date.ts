// 日付ユーティリティ。API は date（"YYYY-MM-DD"）文字列でやり取りする。
// 端末ローカル時刻で「今日」の ISO 文字列を作る（backend は tz 差を +1日まで許容）。

const WEEKDAY_JA = ["日", "月", "火", "水", "木", "金", "土"];

/** ローカル時刻での today を "YYYY-MM-DD" で返す。 */
export function todayISO(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** n 日前の "YYYY-MM-DD"（履歴の from 起点などに使う）。 */
export function isoDaysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** "2026-07-12" → "7/12(日)"（履歴一覧の日付表示）。 */
export function formatShortDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  const wd = WEEKDAY_JA[new Date(y, m - 1, d).getDay()];
  return `${m}/${d}(${wd})`;
}
