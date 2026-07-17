// 過去ログ一括入力の共通ロジック（CSVパース・入力検証）。
//
// オンボーディング Step2（app/(onboarding)/onboarding/page.tsx）と、
// オンボーディング後の後追い一括登録画面（app/(app)/records/import/page.tsx）が
// この同一実装を共有する。重複コピーを作らないための共通モジュール（仕様書 5.3）。
//
// 検証ルールはバックエンド（RecordIn / BulkRecordsIn）と整合させる:
//   - record_date: 実在日・未来日不可（app_today 相当は端末ローカルの todayISO）
//   - actual_score: 1〜10 の整数
//   - 件数上限: 730 件（BULK_MAX_RECORDS と一致）
//   - 同一日付は後勝ちで上書き（bulk も UPSERT のため整合）

import { todayISO } from "./date";

// backend BulkRecordsIn.max_length（約2年分）と一致させる。
export const BULK_MAX = 730;

/** 一括投入1件ぶんの正規化済みレコード。 */
export interface ParsedRecord {
  record_date: string;
  actual_score: number;
  comment: string | null;
}

/** CSVパース結果。 */
export interface ParseResult {
  valid: ParsedRecord[];
  errorCount: number;
  capped: boolean; // 730 件を超えて先頭のみ採用したか。
}

/** "YYYY-MM-DD" 形式かつ実在日で、未来日でないか。 */
export function isValidPastDate(s: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
  const [y, m, d] = s.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  if (dt.getFullYear() !== y || dt.getMonth() !== m - 1 || dt.getDate() !== d) {
    return false;
  }
  return s <= todayISO(); // 文字列比較で OK（ゼロ埋め ISO のため）。未来日は不可。
}

/** スコアが 1〜10 の整数か。 */
export function isValidScore(n: number): boolean {
  return Number.isInteger(n) && n >= 1 && n <= 10;
}

/**
 * CSV「日付,スコア,コメント」をパースする。
 * コメント内のカンマは3分割目以降として保持する。同一日付は後勝ち、730件で cap。
 */
export function parseCsv(text: string): ParseResult {
  const valid: ParsedRecord[] = [];
  let errorCount = 0;
  const seen = new Set<string>();
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (line === "") continue;
    const parts = line.split(",");
    const date = (parts[0] ?? "").trim();
    const scoreStr = (parts[1] ?? "").trim();
    const comment = parts.slice(2).join(",").trim();
    const score = Number(scoreStr);
    if (!isValidPastDate(date) || scoreStr === "" || !isValidScore(score)) {
      errorCount += 1;
      continue;
    }
    if (seen.has(date)) {
      // 同一日付は後勝ちで上書き（bulk も upsert のため整合）。
      const idx = valid.findIndex((v) => v.record_date === date);
      if (idx >= 0) valid.splice(idx, 1);
    }
    seen.add(date);
    valid.push({
      record_date: date,
      actual_score: score,
      comment: comment === "" ? null : comment,
    });
  }
  const capped = valid.length > BULK_MAX;
  return { valid: capped ? valid.slice(0, BULK_MAX) : valid, errorCount, capped };
}

/**
 * 手入力フォームで1日ぶんを既存リストに追加/上書きする純粋関数。
 * 同一日は上書き、日付昇順ソート、730件で cap。検証は呼び出し側で行う前提。
 */
export function upsertManualRecord(
  prev: ParsedRecord[],
  rec: ParsedRecord,
): ParsedRecord[] {
  const next = prev.filter((r) => r.record_date !== rec.record_date);
  next.push(rec);
  next.sort((a, b) => a.record_date.localeCompare(b.record_date));
  return next.slice(0, BULK_MAX);
}
