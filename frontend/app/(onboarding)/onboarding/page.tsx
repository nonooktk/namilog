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

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { namilogApi } from "@/lib/api";
import type { CatalogItem, CatalogResponse, Profile } from "@/lib/types";
import { DisclaimerBar } from "@/components/DisclaimerBar";
import { BulkRecordEntry } from "@/components/BulkRecordEntry";
import { IwashiTaro, IWASHI } from "@/components/IwashiTaro";
import type { ParsedRecord } from "@/lib/records-import";

const MAX_FACTORS = 3;
const TOTAL_STEPS = 4;

// 医療免責文言（デザイン仕様6.4・正本）。
const DISCLAIMER_TEXT =
  "なみログは、体調の記録と傾向の把握をお手伝いするアプリです。医師による診断や治療の代わりになるものではありません。体調に不安があるときは、医療機関にご相談ください。";

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 逆ガード（機能A）: オンボーディング完了済み（onboarded_at != null）が /onboarding に
  // 来たら、ウィザードを再表示せずホームへ送る。(app) 側 OnboardingGate（未完了→/onboarding）の
  // 一方向ガードを壊さず、逆方向を補う。判定失敗時はウィザードを塞がない（degrade）。
  //   "checking": 判定中（ウィザードは出さない） / "pass": 表示 / "redirect": ホームへ送る途中。
  const [guard, setGuard] = useState<"checking" | "pass" | "redirect">(
    "checking",
  );

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const profile = (await namilogApi.getProfile()) as Profile | null;
        if (!mounted) return;
        if (profile && profile.onboarded_at != null) {
          setGuard("redirect");
          router.replace("/");
        } else {
          setGuard("pass");
        }
      } catch {
        // 判定失敗時はウィザードを塞がない（degrade）。
        if (mounted) setGuard("pass");
      }
    })();
    return () => {
      mounted = false;
    };
  }, [router]);

  // ステップ②: 過去ログ入力。入力 UI・検証は BulkRecordEntry（共通）に委譲し、
  // ここでは「いま送信対象になる有効レコード」だけを受け取って保持する。
  const [activeRecords, setActiveRecords] = useState<ParsedRecord[]>([]);

  // ステップ③: 外部情報選択。
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [catalogLoaded, setCatalogLoaded] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);

  // ステップ④: 医療免責同意。
  const [agreed, setAgreed] = useState(false);

  // 同一内容の再送を避けるための直近送信シグネチャ（戻る→進むでの二重送信防止）。
  const savedRecordsSig = useRef<string | null>(null);
  const savedSelSig = useRef<string | null>(null);

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

  // 逆ガード判定中／リダイレクト中はウィザードを描画しない（完了済みユーザーへの一瞬の点滅を防ぐ）。
  if (guard !== "pass") {
    return (
      <div className="center-fill" role="status" aria-live="polite">
        <div className="spinner" aria-hidden="true" />
        <span>読み込み中…</span>
      </div>
    );
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

        {/* イワシ太郎（1画面1箇所）。免責同意ステップ(④)は静かなトーン、それ以外は通常。§11.3 */}
        <IwashiTaro
          message={step === 4 ? IWASHI.onboardingDisclaimer : IWASHI.onboardingNormal}
        />

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

            {/* 入力 UI・パース・検証は共通コンポーネントに委譲（/records/import と共有）。 */}
            <BulkRecordEntry onRecordsChange={setActiveRecords} disabled={busy} />

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
