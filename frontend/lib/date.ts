// 日付ユーティリティ。API は date（"YYYY-MM-DD"）文字列でやり取りする。
// 「今日」「n日前」はアプリ既定 tz（Asia/Tokyo, JST）基準で算出し、バックエンドの
// app_today()（backend/app/timeutils.py）と整合させる（F-2 / コンペ01是正）。
//
// 端末ローカル時刻ではなく JST 固定にする理由:
//   - バックエンドは未来日判定・週境界・today 既定をすべて JST（app_today）で判定する。
//   - フロントもローカル tz だと、非JST端末や深夜帯で今日/未来日の境界がずれ、
//     過剰拒否や差し替え対象の取り違えが起きうる（レビュー指摘 F-2）。
//   - Intl.DateTimeFormat に timeZone を明示するとプロセス/端末 tz に依存しない。
//     日本は夏時間が無いため暦日計算も安定する。

const WEEKDAY_JA = ["日", "月", "火", "水", "木", "金", "土"];

// Asia/Tokyo の暦日を "YYYY-MM-DD" で返す内部フォーマッタ。
// en-CA ロケールは "YYYY-MM-DD" 形式を返す。
const JST_DATE_FMT = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Tokyo",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

/** JST（Asia/Tokyo）での today を "YYYY-MM-DD" で返す。backend app_today() と一致。 */
export function todayISO(): string {
  return JST_DATE_FMT.format(new Date());
}

/** JST 基準で n 日前の "YYYY-MM-DD"（履歴の from 起点などに使う）。 */
export function isoDaysAgo(n: number): string {
  // JST の今日を起点に、UTC 上で日数を引く（日本は夏時間なしのため暦日がずれない）。
  const [y, m, d] = todayISO().split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() - n);
  const yy = dt.getUTCFullYear();
  const mm = String(dt.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(dt.getUTCDate()).padStart(2, "0");
  return `${yy}-${mm}-${dd}`;
}

/** "2026-07-12" → "7/12(日)"（履歴一覧の日付表示）。曜日は日付要素から算出（tz非依存）。 */
export function formatShortDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  const wd = WEEKDAY_JA[new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
  return `${m}/${d}(${wd})`;
}
