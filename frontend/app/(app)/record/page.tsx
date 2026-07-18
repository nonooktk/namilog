"use client";

// 体調入力（NL-API-06: POST /api/records、NL-API-08: PUT /api/factor-values）。
// スコア1〜10（5×2 丸ボタン）＋任意コメント＋アクティブな手入力型指標の入力欄。
// コメント必須化はしない（デザイン5.5）。crisis_notice が true なら相談窓口を案内する。

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { namilogApi } from "@/lib/api";
import type {
  ListRecordsResponse,
  RecordMutationResponse,
  SelectionResponse,
} from "@/lib/types";
import { AppHeader } from "@/components/AppHeader";
import { SupportCard } from "@/components/SupportCard";
import { bandLabel } from "@/lib/score";
import { todayISO } from "@/lib/date";

interface ManualFactor {
  factor_key: string;
  label: string;
  unit: string | null;
}

export default function RecordPage() {
  const router = useRouter();
  const [score, setScore] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [manualFactors, setManualFactors] = useState<ManualFactor[]>([]);
  const [factorValues, setFactorValues] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [crisis, setCrisis] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 当日すでに記録があるか（機能B）。true なら「記録済み→差し替え」表示に切り替える。
  const [alreadyRecorded, setAlreadyRecorded] = useState(false);
  // 直近の保存が差し替え（既存あり）だったか。完了トーストの文言切り替えに使う。
  const [savedAsEdit, setSavedAsEdit] = useState(false);
  // 当日プリフィル（listRecords）の読み込み中か（F-1: プリフィル race 対策）。
  // true の間は送信を抑止し、プリフィル完了前のユーザー入力が後から上書きされる競合を防ぐ。
  const [recordLoading, setRecordLoading] = useState(true);
  // 当日プリフィルの取得に失敗したか（F-3）。無言で新規モードへ落とさず控えめに通知する。
  const [prefillFailed, setPrefillFailed] = useState(false);

  // アクティブな指標のうち手入力型（manual）だけを入力欄に出す（デザイン5.2 / ARCHITECTURE §5.2）。
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const sel = (await namilogApi.getSelection()) as SelectionResponse;
        if (!mounted) return;
        setManualFactors(
          sel.active
            .filter((a) => a.input_type === "manual")
            .map((a) => ({
              factor_key: a.factor_key,
              label: a.label,
              unit: a.unit,
            })),
        );
      } catch {
        // 指標が取れなくても体調入力自体は続行できる（任意項目）。
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  // 当日記録のプリフィル（機能B）。既存の一覧 API を今日1日に絞って再利用する
  // （単日取得 API は追加しない）。RLS は本人トークンでサーバ側解決のまま。
  // 記録があればスコア・コメントを初期値にし、「差し替え」モードにする。無ければ従来どおり空欄。
  useEffect(() => {
    let mounted = true;
    const today = todayISO();
    (async () => {
      try {
        const res = (await namilogApi.listRecords(
          today,
          today,
        )) as ListRecordsResponse;
        if (!mounted) return;
        const todayRow = res.records?.find(
          (r) => r.date === today && r.actual_score != null,
        );
        if (todayRow && todayRow.actual_score != null) {
          setScore(todayRow.actual_score);
          setComment(todayRow.comment ?? "");
          setAlreadyRecorded(true);
        }
      } catch {
        // 取得失敗時も新規登録として続行できる（プリフィルは補助）。ただし F-3:
        // 無言で degrade せず、控えめに「確認できなかった」旨を通知する。
        if (mounted) setPrefillFailed(true);
      } finally {
        // F-1: 読み込み完了で送信抑止を解除する（成功・失敗どちらでも必ず通す）。
        if (mounted) setRecordLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  function setFactor(key: string, value: string) {
    setFactorValues((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit() {
    if (score == null) return;
    setSubmitting(true);
    setError(null);
    setCrisis(false);
    const date = todayISO();
    try {
      const res = (await namilogApi.createRecord({
        record_date: date,
        actual_score: score,
        comment: comment.trim() === "" ? null : comment.trim(),
      })) as RecordMutationResponse;

      // 手入力の外部指標値があればマージ保存（数値化できるものは数値で送る）。
      const values: Record<string, unknown> = {};
      for (const [k, raw] of Object.entries(factorValues)) {
        const t = raw.trim();
        if (t === "") continue;
        const num = Number(t);
        values[k] = t !== "" && !Number.isNaN(num) ? num : t;
      }
      if (Object.keys(values).length > 0) {
        await namilogApi.putFactorValues(date, values);
      }

      setCrisis(res.crisis_notice);
      setSavedAsEdit(alreadyRecorded); // 保存前に既存があったか＝差し替え保存だったか。
      setDone(true);
      // 保存後は当日記録が存在する状態になるので、以降は「差し替え」表示に統一する。
      setAlreadyRecorded(true);
    } catch {
      setError("記録を保存できませんでした。通信状況を確認してもう一度試してね。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <AppHeader title="体調入力" back />
      <main className="screen">
        <h1 className="screen-title">
          {alreadyRecorded ? "今日の記録を差し替え" : "今日の記録"}
        </h1>

        {/* F-1: 当日プリフィルの読み込み中を控えめに提示。この間は送信も抑止する。 */}
        {recordLoading && (
          <p className="field-hint" aria-live="polite">
            今日の記録を確認中…
          </p>
        )}

        {/* F-3: プリフィル取得に失敗したときは無言にせず、控えめに知らせる（アラートは過剰）。 */}
        {prefillFailed && !done && (
          <p className="field-hint" aria-live="polite">
            今日の記録を確認できなかったよ。新しく記録することはできるよ。
          </p>
        )}

        {/* 当日すでに記録済みのときは、新規登録ではなく差し替え（上書き）だと明示する（機能B）。 */}
        {alreadyRecorded && !done && (
          <p className="error-note" role="note">
            今日はもう記録があるよ。内容を直して保存すると、今日の記録が
            <strong>差し替え</strong>られるね。
          </p>
        )}

        {done && (
          <p className="toast" role="status">
            {savedAsEdit
              ? "記録を差し替えたよ。教えてくれてありがとう。"
              : "記録したよ。教えてくれてありがとう。"}
          </p>
        )}
        {crisis && <SupportCard />}
        {error && (
          <p className="error-note" role="alert">
            {error}
          </p>
        )}

        <div className="card">
          <label className="field-label" id="score-label">
            今日の体調は、10点満点でどのくらい？
          </label>
          <div
            className="score-picker"
            role="group"
            aria-labelledby="score-label"
          >
            {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
              <button
                key={n}
                type="button"
                className={`score-btn${score === n ? " selected" : ""}`}
                aria-pressed={score === n}
                onClick={() => setScore(n)}
              >
                {n}
              </button>
            ))}
          </div>
          {score != null && (
            <div className="field-hint">
              選択中: {score}点「{bandLabel(score)}」
            </div>
          )}
        </div>

        <div className="card">
          <label className="field-label" htmlFor="comment">
            今日感じたことを、気が向いたら書いてね（空欄でもOK）
          </label>
          <textarea
            id="comment"
            className="input-area"
            placeholder="例）朝は少しだるかったけど、午後から落ち着いた"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </div>

        {manualFactors.length > 0 && (
          <div className="card">
            <h2 className="card-title">今日の外部指標（任意）</h2>
            {manualFactors.map((f) => (
              <div className="factor-field" key={f.factor_key}>
                <label className="field-label" htmlFor={`factor-${f.factor_key}`}>
                  {f.label}
                  {f.unit ? `（${f.unit}）` : ""}
                </label>
                <input
                  id={`factor-${f.factor_key}`}
                  className="factor-input"
                  type="text"
                  inputMode="text"
                  placeholder={f.unit ? `例）${f.unit} を入力` : "入力（任意）"}
                  value={factorValues[f.factor_key] ?? ""}
                  onChange={(e) => setFactor(f.factor_key, e.target.value)}
                />
              </div>
            ))}
          </div>
        )}

        <button
          className="btn btn-primary btn-block"
          onClick={handleSubmit}
          // F-1: プリフィル完了前（recordLoading）は送信を抑止し、読み込み結果が
          // ユーザー入力を上書きする競合／未確認のまま誤送信するのを防ぐ。
          disabled={score == null || submitting || recordLoading}
        >
          {submitting
            ? "保存中…"
            : recordLoading
              ? "確認中…"
              : alreadyRecorded
                ? "この内容に差し替える"
                : "記録する"}
        </button>
        <div style={{ height: 12 }} />
        <button
          className="btn btn-secondary btn-block"
          onClick={() => router.push("/")}
          disabled={submitting}
        >
          あとで入力する
        </button>
      </main>
    </>
  );
}
