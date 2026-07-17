"use client";

// 過去ログ一括入力の共通入力コンポーネント（CSV貼り付け／1件ずつ入力のタブ）。
//
// オンボーディング Step2 と、後追い一括登録画面（/records/import）が共有する（仕様書 5.3）。
// パース・検証ロジックは lib/records-import.ts に集約し、このコンポーネントは入力 UI と
// 「いま送信対象になる有効レコード」の算出だけを担う（送信・画面遷移は呼び出し側の責務）。
//
// 状態は自コンポーネント内に閉じ、有効レコードが変わるたび onRecordsChange で親へ通知する。

import { useEffect, useMemo, useState } from "react";
import { todayISO } from "@/lib/date";
import {
  BULK_MAX,
  isValidPastDate,
  isValidScore,
  parseCsv,
  upsertManualRecord,
  type ParsedRecord,
} from "@/lib/records-import";

interface Props {
  /** 有効な送信対象レコードが変わるたびに呼ばれる。親はこれを保存に使う。 */
  onRecordsChange: (records: ParsedRecord[]) => void;
  /** 入力操作を無効化する（送信中など）。 */
  disabled?: boolean;
}

export function BulkRecordEntry({ onRecordsChange, disabled = false }: Props) {
  const [tab, setTab] = useState<"csv" | "manual">("csv");
  const [csvText, setCsvText] = useState("");
  const [manual, setManual] = useState<ParsedRecord[]>([]);
  const [mDate, setMDate] = useState("");
  const [mScore, setMScore] = useState("");
  const [mComment, setMComment] = useState("");
  const [mError, setMError] = useState<string | null>(null);

  const parsed = useMemo(() => parseCsv(csvText), [csvText]);

  // いま送信対象になる有効レコード（アクティブタブ由来）。
  const activeRecords: ParsedRecord[] = tab === "csv" ? parsed.valid : manual;

  // 有効レコードが変わったら親へ通知（タブ切り替え・入力編集の両方を拾う）。
  useEffect(() => {
    onRecordsChange(activeRecords);
    // activeRecords は毎回新配列だが、中身が同じなら親側で無害。依存は実データに絞る。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, csvText, manual]);

  function addManual() {
    setMError(null);
    const date = mDate.trim();
    const score = Number(mScore);
    if (!isValidPastDate(date)) {
      setMError("日付は今日以前の実在する日で入力してね（例: 2026-06-01）。");
      return;
    }
    if (mScore.trim() === "" || !isValidScore(score)) {
      setMError("スコアは1〜10の整数で選んでね。");
      return;
    }
    setManual((prev) =>
      upsertManualRecord(prev, {
        record_date: date,
        actual_score: score,
        comment: mComment.trim() === "" ? null : mComment.trim(),
      }),
    );
    setMDate("");
    setMScore("");
    setMComment("");
  }

  function removeManual(date: string) {
    setManual((prev) => prev.filter((r) => r.record_date !== date));
  }

  return (
    <>
      <div className="tab-row" role="tablist" aria-label="入力方法">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "csv"}
          className={`tab-btn${tab === "csv" ? " active" : ""}`}
          onClick={() => setTab("csv")}
          disabled={disabled}
        >
          CSVで貼り付け
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "manual"}
          className={`tab-btn${tab === "manual" ? " active" : ""}`}
          onClick={() => setTab("manual")}
          disabled={disabled}
        >
          1件ずつ入力
        </button>
      </div>

      {tab === "csv" ? (
        <>
          <label className="field-label" htmlFor="csv-input">
            1行につき「日付,スコア,コメント」の形で貼り付けてね（コメントは省略可）。
          </label>
          <textarea
            id="csv-input"
            className="csv-area"
            placeholder={
              "2026-06-01,5,少し疲れ気味\n2026-06-02,7,調子良い\n2026-06-03,4,雨で気分沈みがち"
            }
            value={csvText}
            onChange={(e) => setCsvText(e.target.value)}
            disabled={disabled}
          />
          {csvText.trim() !== "" && (
            <>
              <p className="field-hint" aria-live="polite">
                取り込める行: {parsed.valid.length}件
                {parsed.errorCount > 0 &&
                  `（読み取れなかった行: ${parsed.errorCount}件はスキップするよ）`}
                {parsed.capped && `（多いので先頭${BULK_MAX}件までにするね）`}
              </p>
              {parsed.valid.length > 0 && (
                <div className="log-preview" aria-label="取り込みプレビュー">
                  {parsed.valid.slice(0, 5).map((r) => (
                    <div className="log-preview-row" key={r.record_date}>
                      <span className="d">{r.record_date}</span>
                      <span className="s">{r.actual_score}点</span>
                      <span className="c">{r.comment ?? ""}</span>
                    </div>
                  ))}
                  {parsed.valid.length > 5 && (
                    <div className="log-preview-row">
                      <span className="c">…ほか {parsed.valid.length - 5}件</span>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </>
      ) : (
        <>
          <div className="manual-form">
            <div className="manual-field">
              <label className="field-label" htmlFor="m-date">
                日付
              </label>
              <input
                id="m-date"
                className="manual-input"
                type="date"
                max={todayISO()}
                value={mDate}
                onChange={(e) => setMDate(e.target.value)}
                disabled={disabled}
              />
            </div>
            <div className="manual-field">
              <label className="field-label" htmlFor="m-score">
                その日の体調（1〜10）
              </label>
              <select
                id="m-score"
                className="manual-input"
                value={mScore}
                onChange={(e) => setMScore(e.target.value)}
                disabled={disabled}
              >
                <option value="">選んでね</option>
                {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </div>
            <div className="manual-field">
              <label className="field-label" htmlFor="m-comment">
                コメント（任意）
              </label>
              <input
                id="m-comment"
                className="manual-input"
                type="text"
                placeholder="例）よく眠れた"
                value={mComment}
                onChange={(e) => setMComment(e.target.value)}
                disabled={disabled}
              />
            </div>
            {mError && (
              <p className="error-note" role="alert">
                {mError}
              </p>
            )}
            <button
              type="button"
              className="btn btn-secondary btn-block"
              onClick={addManual}
              disabled={disabled}
            >
              この日を追加する
            </button>
          </div>

          {manual.length > 0 && (
            <div className="log-preview" aria-label="追加した記録">
              {manual.map((r) => (
                <div className="log-preview-row" key={r.record_date}>
                  <span className="d">{r.record_date}</span>
                  <span className="s">{r.actual_score}点</span>
                  <span className="c">{r.comment ?? ""}</span>
                  <button
                    type="button"
                    className="log-remove"
                    aria-label={`${r.record_date} の記録を削除`}
                    onClick={() => removeManual(r.record_date)}
                    disabled={disabled}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </>
  );
}
