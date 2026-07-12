"use client";

// オンボーディング（デザイン仕様8-1 / mockup.html「はじめまして」画面）。
// Google ログイン後に到達する 4 ステップのウィザード。
//   ① ようこそ（あいさつ・アプリ説明）
//   ② これまでの記録を一括入力（任意。CSV 貼り付け／1件ずつ入力）→ 有効行を bulkRecords 送信
//   ③ 予測に使う外部情報を 12 候補から 3 つ選ぶ → putSelection
//   ④ 医療免責への同意（チェック必須）→ updateProfile で同意＝オンボーディング完了を記録
//
// 完了判定は profiles.onboarded_at（正）。バックエンドの PUT /api/profile は onboarded_at を
// 直接受け取らず、agree_medical_disclaimer=true を送ると server 側で onboarded_at と
// medical_disclaimer_agreed_at を now() 記録する（backend/app/routers/profile.py）。
// そのため④では { agree_medical_disclaimer:true, timezone } を送る。

import { useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { namilogApi } from "@/lib/api";
import type { CatalogItem, CatalogResponse } from "@/lib/types";
import { todayISO } from "@/lib/date";
import { DisclaimerBar } from "@/components/DisclaimerBar";

const MAX_FACTORS = 3;
const BULK_MAX = 730; // backend BulkRecordsIn.max_length と一致（約2年分）。
const TOTAL_STEPS = 4;

// 医療免責文言（デザイン仕様6.4・正本）。
const DISCLAIMER_TEXT =
  "なみログは、体調の記録と傾向の把握をお手伝いするアプリです。医師による診断や治療の代わりになるものではありません。体調に不安があるときは、医療機関にご相談ください。";

interface ParsedRecord {
  record_date: string;
  actual_score: number;
  comment: string | null;
}
interface ParseResult {
  valid: ParsedRecord[];
  errorCount: number;
  capped: boolean; // 730 件を超えて先頭のみ採用したか。
}

// "YYYY-MM-DD" 形式かつ実在日で、未来日でないか。
function isValidPastDate(s: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
  const [y, m, d] = s.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  if (
    dt.getFullYear() !== y ||
    dt.getMonth() !== m - 1 ||
    dt.getDate() !== d
  ) {
    return false;
  }
  return s <= todayISO(); // 文字列比較で OK（ゼロ埋め ISO のため）。未来日は不可。
}

function isValidScore(n: number): boolean {
  return Number.isInteger(n) && n >= 1 && n <= 10;
}

// CSV「日付,スコア,コメント」をパースする。コメント内のカンマは3分割目以降として保持する。
function parseCsv(text: string): ParseResult {
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

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ステップ②: 過去ログ入力。
  const [tab, setTab] = useState<"csv" | "manual">("csv");
  const [csvText, setCsvText] = useState("");
  const [manual, setManual] = useState<ParsedRecord[]>([]);
  const [mDate, setMDate] = useState("");
  const [mScore, setMScore] = useState("");
  const [mComment, setMComment] = useState("");
  const [mError, setMError] = useState<string | null>(null);

  // ステップ③: 外部情報選択。
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [catalogLoaded, setCatalogLoaded] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);

  // ステップ④: 医療免責同意。
  const [agreed, setAgreed] = useState(false);

  // 同一内容の再送を避けるための直近送信シグネチャ（戻る→進むでの二重送信防止）。
  const savedRecordsSig = useRef<string | null>(null);
  const savedSelSig = useRef<string | null>(null);

  const parsed = useMemo(() => parseCsv(csvText), [csvText]);

  // いま送信対象になる有効レコード（アクティブタブ由来）。
  const activeRecords: ParsedRecord[] = tab === "csv" ? parsed.valid : manual;

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
    setManual((prev) => {
      const next = prev.filter((r) => r.record_date !== date); // 同一日は上書き。
      next.push({
        record_date: date,
        actual_score: score,
        comment: mComment.trim() === "" ? null : mComment.trim(),
      });
      next.sort((a, b) => a.record_date.localeCompare(b.record_date));
      return next.slice(0, BULK_MAX);
    });
    setMDate("");
    setMScore("");
    setMComment("");
  }

  function removeManual(date: string) {
    setManual((prev) => prev.filter((r) => r.record_date !== date));
  }

  // ステップ③のカタログは初回表示時に読み込む（②から③へ進むタイミング）。
  async function loadCatalog() {
    if (catalogLoaded) return;
    try {
      const res = (await namilogApi.getCatalog()) as CatalogResponse;
      const items = (res.catalog ?? [])
        .slice()
        .sort((a, b) => a.sort_order - b.sort_order);
      setCatalog(items);
      setCatalogLoaded(true);
    } catch {
      // 取得失敗時は空のまま（③で読み込みエラーを表示し、再試行導線を出す）。
      setCatalogLoaded(true);
      setError("外部情報の候補を読み込めませんでした。通信状況を確認してね。");
    }
  }

  function toggleFactor(key: string) {
    setSelected((prev) => {
      if (prev.includes(key)) return prev.filter((k) => k !== key);
      if (prev.length >= MAX_FACTORS) return prev; // 3件を超えて選べない。
      return [...prev, key];
    });
  }

  async function goNext() {
    setError(null);
    if (step === 1) {
      setStep(2);
      return;
    }

    if (step === 2) {
      // 有効行があれば一括保存（なければスキップ扱いでそのまま次へ）。
      if (activeRecords.length > 0) {
        const sig = JSON.stringify(activeRecords);
        if (savedRecordsSig.current !== sig) {
          setBusy(true);
          try {
            await namilogApi.bulkRecords(activeRecords);
            savedRecordsSig.current = sig;
          } catch {
            setError("これまでの記録を保存できませんでした。もう一度試すか、スキップして進んでね。");
            setBusy(false);
            return;
          }
          setBusy(false);
        }
      }
      await loadCatalog();
      setStep(3);
      return;
    }

    if (step === 3) {
      if (selected.length !== MAX_FACTORS) return; // ボタン側でも無効化。
      const sig = JSON.stringify([...selected].sort());
      if (savedSelSig.current !== sig) {
        setBusy(true);
        try {
          await namilogApi.putSelection(selected);
          savedSelSig.current = sig;
        } catch {
          setError("選んだ情報を保存できませんでした。3つ選べているか確認して、もう一度試してね。");
          setBusy(false);
          return;
        }
        setBusy(false);
      }
      setStep(4);
      return;
    }
  }

  function goBack() {
    setError(null);
    setStep((s) => Math.max(1, s - 1));
  }

  // ステップ②をスキップ（保存せず③へ）。
  async function skipStep2() {
    setError(null);
    await loadCatalog();
    setStep(3);
  }

  // ④「はじめる」: 免責同意＝オンボーディング完了を記録し、ホームへ。
  async function finish() {
    if (!agreed) return;
    setError(null);
    setBusy(true);
    // 端末のタイムゾーン（取れなければアプリ既定の Asia/Tokyo）。
    let tz = "Asia/Tokyo";
    try {
      const resolved = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (resolved) tz = resolved;
    } catch {
      // 取得失敗時は既定のまま。
    }
    try {
      await namilogApi.updateProfile({
        agree_medical_disclaimer: true, // server が onboarded_at / 同意時刻を now() 記録。
        timezone: tz,
      });
    } catch {
      setError("はじめる処理に失敗しました。通信状況を確認して、もう一度試してね。");
      setBusy(false);
      return;
    }
    // 完了。ホームへ。(app) の OnboardingGate が onboarded_at 済みを確認して通す。
    router.replace("/");
  }

  return (
    <>
      <main className="screen">
        <h1 className="screen-title">はじめまして</h1>

        {/* ステップインジケーター（控えめに現在地を示す）。 */}
        <div
          className="step-indicator"
          role="progressbar"
          aria-valuemin={1}
          aria-valuemax={TOTAL_STEPS}
          aria-valuenow={step}
          aria-label={`ステップ ${step} / ${TOTAL_STEPS}`}
        >
          {Array.from({ length: TOTAL_STEPS }, (_, i) => i + 1).map((n) => (
            <div
              key={n}
              className={`step-dot${n < step ? " done" : n === step ? " active" : ""}`}
            />
          ))}
        </div>

        {error && (
          <p className="error-note" role="alert">
            {error}
          </p>
        )}

        {/* ===== ステップ①: ようこそ ===== */}
        {step === 1 && (
          <div className="step-section">
            <div className="step-heading">
              <div className="step-num" aria-hidden="true">
                1
              </div>
              <h2>ようこそ、なみログへ</h2>
            </div>
            <p className="step-lead">
              なみログは、あなたの体調の波をそっと記録して、これからの傾向をやさしくお知らせするアプリだよ。
              まずは、いっしょに数ステップだけ準備しよう。むずかしいことはないから安心してね。
            </p>
            <div className="onboard-nav">
              <button className="btn btn-primary btn-block" onClick={goNext}>
                はじめる
              </button>
            </div>
          </div>
        )}

        {/* ===== ステップ②: これまでの記録（任意） ===== */}
        {step === 2 && (
          <div className="step-section">
            <div className="step-heading">
              <div className="step-num" aria-hidden="true">
                2
              </div>
              <h2>これまでの記録を入力（任意）</h2>
            </div>
            <p className="step-lead">
              手元に過去の記録があれば、まとめて取り込めるよ。なければ空欄のまま次に進んでも大丈夫。
            </p>

            <div className="tab-row" role="tablist" aria-label="入力方法">
              <button
                type="button"
                role="tab"
                aria-selected={tab === "csv"}
                className={`tab-btn${tab === "csv" ? " active" : ""}`}
                onClick={() => setTab("csv")}
              >
                CSVで貼り付け
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={tab === "manual"}
                className={`tab-btn${tab === "manual" ? " active" : ""}`}
                onClick={() => setTab("manual")}
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
                            <span className="c">
                              …ほか {parsed.valid.length - 5}件
                            </span>
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
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}

            <div className="onboard-nav">
              <button
                className="btn btn-secondary"
                onClick={goBack}
                disabled={busy}
              >
                戻る
              </button>
              {activeRecords.length > 0 ? (
                <button
                  className="btn btn-primary"
                  onClick={goNext}
                  disabled={busy}
                >
                  {busy ? "保存中…" : `${activeRecords.length}件を保存して次へ`}
                </button>
              ) : (
                <button
                  className="btn btn-primary"
                  onClick={skipStep2}
                  disabled={busy}
                >
                  スキップして次へ
                </button>
              )}
            </div>
          </div>
        )}

        {/* ===== ステップ③: 外部情報を3つ選ぶ ===== */}
        {step === 3 && (
          <div className="step-section">
            <div className="step-heading">
              <div className="step-num" aria-hidden="true">
                3
              </div>
              <h2>予測に使う情報を3つ選ぶ</h2>
            </div>
            <p className="step-lead">
              12個の候補から、あなたの体調と関係していそうなものを3つ選んでね。後からいつでも変えられるよ。
            </p>

            {!catalogLoaded ? (
              <div className="card" aria-busy="true">
                <p className="empty-note">読み込み中…</p>
              </div>
            ) : catalog.length === 0 ? (
              <div className="card">
                <p className="empty-note">
                  候補を読み込めなかったみたい。
                </p>
                <button
                  className="btn btn-secondary btn-block"
                  onClick={() => {
                    setCatalogLoaded(false);
                    setError(null);
                    void loadCatalog();
                  }}
                >
                  もう一度読み込む
                </button>
              </div>
            ) : (
              <>
                <div className="selection-count" aria-live="polite">
                  選択中: {selected.length} / {MAX_FACTORS}
                </div>
                <div
                  className="chip-grid"
                  role="group"
                  aria-label="予測に使う情報の候補"
                >
                  {catalog.map((c) => {
                    const isSel = selected.includes(c.factor_key);
                    const disabled = !isSel && selected.length >= MAX_FACTORS;
                    return (
                      <button
                        key={c.factor_key}
                        type="button"
                        className={`chip${isSel ? " selected" : ""}`}
                        aria-pressed={isSel}
                        disabled={disabled}
                        onClick={() => toggleFactor(c.factor_key)}
                      >
                        {c.label}
                      </button>
                    );
                  })}
                </div>
              </>
            )}

            <div className="onboard-nav">
              <button
                className="btn btn-secondary"
                onClick={goBack}
                disabled={busy}
              >
                戻る
              </button>
              <button
                className="btn btn-primary"
                onClick={goNext}
                disabled={busy || selected.length !== MAX_FACTORS}
              >
                {busy ? "保存中…" : "次へ"}
              </button>
            </div>
          </div>
        )}

        {/* ===== ステップ④: 医療免責への同意 ===== */}
        {step === 4 && (
          <div className="step-section">
            <div className="step-heading">
              <div className="step-num" aria-hidden="true">
                4
              </div>
              <h2>内容を確認して、はじめよう</h2>
            </div>

            <div className="disclaimer-bar" style={{ marginBottom: 12 }}>
              {DISCLAIMER_TEXT}
            </div>

            <label className="consent-check">
              <input
                type="checkbox"
                checked={agreed}
                aria-describedby="consent-note"
                onChange={(e) => setAgreed(e.target.checked)}
              />
              <span>内容を理解しました</span>
            </label>
            <p
              id="consent-note"
              className="field-hint"
              style={{ marginTop: 4, marginBottom: 16 }}
            >
              読んでから、いっしょにはじめようね。
            </p>

            <div className="onboard-nav">
              <button
                className="btn btn-secondary"
                onClick={goBack}
                disabled={busy}
              >
                戻る
              </button>
              <button
                className="btn btn-primary"
                onClick={finish}
                disabled={busy || !agreed}
              >
                {busy ? "準備中…" : "はじめる"}
              </button>
            </div>
          </div>
        )}
      </main>

      <DisclaimerBar />
    </>
  );
}
