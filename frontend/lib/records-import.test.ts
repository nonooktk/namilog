// 過去ログ一括入力の共通ロジックの単体テスト（F-4）。
// parseCsv / isValidPastDate / isValidScore / upsertManualRecord の正常系・境界・異常系を固定する。
// 日付境界は JST 基準（todayISO / isoDaysAgo。date.ts）に統一済み（F-2）。

import { describe, it, expect } from "vitest";
import {
  BULK_MAX,
  isValidPastDate,
  isValidScore,
  parseCsv,
  upsertManualRecord,
  type ParsedRecord,
} from "./records-import";
import { todayISO, isoDaysAgo } from "./date";

// JST 基準の相対日付（実行時刻に依存せず境界を作れる）。
const TODAY = todayISO();
const YESTERDAY = isoDaysAgo(1);
const TOMORROW = isoDaysAgo(-1);

/** 過去の実在日を n 件生成する（2000-01-01 から連番。すべて過去日・ユニーク）。 */
function pastDates(n: number): string[] {
  const base = new Date(Date.UTC(2000, 0, 1));
  const out: string[] = [];
  for (let i = 0; i < n; i++) {
    const d = new Date(base);
    d.setUTCDate(d.getUTCDate() + i);
    out.push(d.toISOString().slice(0, 10));
  }
  return out;
}

describe("isValidPastDate", () => {
  it("実在する過去日を受理する", () => {
    expect(isValidPastDate("2020-06-01")).toBe(true);
    expect(isValidPastDate(YESTERDAY)).toBe(true);
  });

  it("今日（JST）を受理する（未来ではない）", () => {
    expect(isValidPastDate(TODAY)).toBe(true);
  });

  it("未来日（JST基準の明日）を拒否する", () => {
    expect(isValidPastDate(TOMORROW)).toBe(false);
    expect(isValidPastDate("2999-12-31")).toBe(false);
  });

  it("形式不正を拒否する", () => {
    expect(isValidPastDate("2020-6-1")).toBe(false); // ゼロ埋めなし
    expect(isValidPastDate("2020/06/01")).toBe(false); // 区切り違い
    expect(isValidPastDate("not-a-date")).toBe(false);
    expect(isValidPastDate("")).toBe(false);
  });

  it("存在しない日付を拒否する", () => {
    expect(isValidPastDate("2021-02-30")).toBe(false); // 2月30日は無い
    expect(isValidPastDate("2020-13-01")).toBe(false); // 13月は無い
    expect(isValidPastDate("2020-00-10")).toBe(false); // 0月は無い
  });
});

describe("isValidScore", () => {
  it("1〜10の整数を受理する", () => {
    expect(isValidScore(1)).toBe(true);
    expect(isValidScore(10)).toBe(true);
    expect(isValidScore(5)).toBe(true);
  });

  it("範囲外・非整数・非数を拒否する", () => {
    expect(isValidScore(0)).toBe(false);
    expect(isValidScore(11)).toBe(false);
    expect(isValidScore(5.5)).toBe(false);
    expect(isValidScore(NaN)).toBe(false);
    expect(isValidScore(-3)).toBe(false);
  });
});

describe("parseCsv", () => {
  it("正常系: 複数行をパースする", () => {
    const res = parseCsv("2020-01-01,5,少し疲れ気味\n2020-01-02,7,調子良い");
    expect(res.errorCount).toBe(0);
    expect(res.capped).toBe(false);
    expect(res.valid).toEqual([
      { record_date: "2020-01-01", actual_score: 5, comment: "少し疲れ気味" },
      { record_date: "2020-01-02", actual_score: 7, comment: "調子良い" },
    ]);
  });

  it("コメント省略時は null になる", () => {
    const res = parseCsv("2020-01-01,5");
    expect(res.valid[0].comment).toBeNull();
  });

  it("コメント内のカンマを保持する（3分割目以降を連結）", () => {
    const res = parseCsv("2020-01-01,5,hello, world, again");
    expect(res.valid[0].comment).toBe("hello, world, again");
  });

  it("空行はスキップする（errorCount に数えない）", () => {
    const res = parseCsv("\n2020-01-01,5\n\n  \n2020-01-02,6\n");
    expect(res.valid).toHaveLength(2);
    expect(res.errorCount).toBe(0);
  });

  it("不正行はスキップして errorCount に数える", () => {
    const res = parseCsv(
      [
        "2020-01-01,5", // ok
        "2020-01-02,0", // スコア範囲外
        "2020-01-03,abc", // スコア非数
        "bad-date,5", // 日付不正
        "2999-12-31,5", // 未来日
        "2020-01-04", // スコア欠落
      ].join("\n"),
    );
    expect(res.valid.map((r) => r.record_date)).toEqual(["2020-01-01"]);
    expect(res.errorCount).toBe(5);
  });

  it("同一日付は後勝ちで値を上書きし、初出位置を保つ（F-7）", () => {
    const res = parseCsv(
      "2020-01-01,3,古い\n2020-01-02,8,別日\n2020-01-01,9,新しい",
    );
    expect(res.valid).toEqual([
      { record_date: "2020-01-01", actual_score: 9, comment: "新しい" },
      { record_date: "2020-01-02", actual_score: 8, comment: "別日" },
    ]);
  });

  it("境界: ちょうど730件は cap されない", () => {
    const text = pastDates(BULK_MAX)
      .map((d) => `${d},5`)
      .join("\n");
    const res = parseCsv(text);
    expect(res.valid).toHaveLength(BULK_MAX);
    expect(res.capped).toBe(false);
  });

  it("境界: 731件は先頭730件に cap される", () => {
    const text = pastDates(BULK_MAX + 1)
      .map((d) => `${d},5`)
      .join("\n");
    const res = parseCsv(text);
    expect(res.valid).toHaveLength(BULK_MAX);
    expect(res.capped).toBe(true);
  });
});

describe("upsertManualRecord", () => {
  const rec = (d: string, s: number, c: string | null = null): ParsedRecord => ({
    record_date: d,
    actual_score: s,
    comment: c,
  });

  it("新規日付を追加し、日付昇順にソートする", () => {
    let list: ParsedRecord[] = [];
    list = upsertManualRecord(list, rec("2020-01-03", 5)).records;
    const out = upsertManualRecord(list, rec("2020-01-01", 6));
    expect(out.rejected).toBe(false);
    expect(out.records.map((r) => r.record_date)).toEqual([
      "2020-01-01",
      "2020-01-03",
    ]);
  });

  it("同一日付は件数を増やさず上書きする", () => {
    const prev = [rec("2020-01-01", 3, "旧")];
    const out = upsertManualRecord(prev, rec("2020-01-01", 9, "新"));
    expect(out.rejected).toBe(false);
    expect(out.records).toEqual([rec("2020-01-01", 9, "新")]);
  });

  it("境界: 上限到達後の新規日付は拒否し、リストを変更しない（F-5）", () => {
    const prev = pastDates(BULK_MAX).map((d) => rec(d, 5));
    const out = upsertManualRecord(prev, rec(TODAY, 7));
    expect(out.rejected).toBe(true);
    expect(out.records).toBe(prev); // 同一参照＝無変更
  });

  it("境界: 上限到達でも既存日付の上書きは許可する", () => {
    const dates = pastDates(BULK_MAX);
    const prev = dates.map((d) => rec(d, 5));
    const out = upsertManualRecord(prev, rec(dates[0], 10, "上書き"));
    expect(out.rejected).toBe(false);
    expect(out.records).toHaveLength(BULK_MAX);
    expect(out.records.find((r) => r.record_date === dates[0])?.actual_score).toBe(
      10,
    );
  });
});
