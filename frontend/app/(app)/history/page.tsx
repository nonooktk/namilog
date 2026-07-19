"use client";

// 詳細履歴（NL-API-10: GET /api/history/series、NL-API-09: GET /api/records、
// NL-API-19: POST /api/digest）。
// 波グラフ（実測=実線・予測=破線・SVG 自前描画）＋一覧＋期間ダイジェスト。
// 期間はプリセット（7/30/90日）＋カスタム（from/to）で選び、波グラフ・一覧・ダイジェストが連動する。
// イワシ太郎（デザイン §11）は 1 画面 1 箇所。状態で文言を出し分ける（振り返り／生成前／生成後）。

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { namilogApi, ApiError } from "@/lib/api";
import type {
  ListRecordsResponse,
  SeriesResponse,
  SeriesPoint,
  HistoryRow,
  DigestResponse,
} from "@/lib/types";
import { AppHeader } from "@/components/AppHeader";
import { WaveChart } from "@/components/WaveChart";
import { GentleLoader } from "@/components/GentleLoader";
import { IwashiTaro, IWASHI } from "@/components/IwashiTaro";
import { formatShortDate, isoDaysAgo, todayISO } from "@/lib/date";

// 期間プリセット（日数・両端含む）。90日は backend の期間上限92日以内（§4.6）。
const PRESETS = [
  { days: 7, label: "7日" },
  { days: 30, label: "30日" },
  { days: 90, label: "90日" },
] as const;
const DIGEST_MAX_DAYS = 92; // backend DIGEST_MAX_DAYS と一致。

/** ISO 日付 from〜to の両端含む日数を返す（JST 前提・夏時間なしで安定）。 */
function spanDays(from: string, to: string): number {
  const [fy, fm, fd] = from.split("-").map(Number);
  const [ty, tm, td] = to.split("-").map(Number);
  const a = Date.UTC(fy, fm - 1, fd);
  const b = Date.UTC(ty, tm - 1, td);
  return Math.round((b - a) / 86400000) + 1;
}

export default function HistoryPage() {
  // 期間選択。既定は 30 日プリセット（従来の履歴既定を踏襲）。
  const [presetDays, setPresetDays] = useState<number | "custom">(30);
  const [from, setFrom] = useState<string>(isoDaysAgo(29));
  const [to, setTo] = useState<string>(todayISO());

  const [series, setSeries] = useState<SeriesPoint[]>([]);
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ダイジェスト（NL-API-19）。期間を変えたらクリアし、明示ボタンで生成する。
  const [digest, setDigest] = useState<DigestResponse | null>(null);
  const [digestLoading, setDigestLoading] = useState(false);
  const [digestError, setDigestError] = useState<string | null>(null);
  // 生成中に期間が変わったときのレース対策（F-5）。応答が現在の選択と一致する場合のみ反映する。
  const periodRef = useRef({ from, to });
  useEffect(() => {
    periodRef.current = { from, to };
  }, [from, to]);

  // プリセット選択で from/to を算出する（両端含む days 日間）。
  function selectPreset(days: number) {
    setPresetDays(days);
    setFrom(isoDaysAgo(days - 1));
    setTo(todayISO());
  }

  // 波グラフ・一覧は選択期間に連動して取得する。
  useEffect(() => {
    let mounted = true;
    (async () => {
      setLoading(true);
      // 期間が変わったら、その期間のダイジェスト表示はリセット（別期間の結果を残さない）。
      // 生成中に期間を変えた場合もここでローディングを畳む（旧期間の生成は下の staleness で無視）。
      setDigest(null);
      setDigestError(null);
      setDigestLoading(false);
      try {
        const [s, r] = await Promise.all([
          namilogApi.getSeries(from, to) as Promise<SeriesResponse>,
          namilogApi.listRecords(from, to) as Promise<ListRecordsResponse>,
        ]);
        if (!mounted) return;
        setSeries(s.series ?? []);
        setRows(r.records ?? []);
        setError(null);
      } catch {
        if (mounted) setError("履歴を読み込めませんでした。通信状況を確認してね。");
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [from, to]);

  const hasSeries = series.some((p) => p.actual != null || p.predicted != null);
  // 実測のある行のみ一覧に出す（予測だけの未来日行は履歴一覧に混ぜない）。
  const listRows = rows.filter((r) => r.actual_score != null);
  const today = todayISO();

  // ダイジェスト生成可否（backend と同じ制約をフロントでも軽く点検し、無駄な 422 を避ける）。
  const span = useMemo(() => spanDays(from, to), [from, to]);
  const periodValid = from <= to && to <= today && span <= DIGEST_MAX_DAYS;
  // 期間内に実測が1件でもあるか（0 件は backend 422。ボタンを控えめに無効化する）。
  const hasActualInPeriod = listRows.length > 0;

  async function makeDigest(force = false) {
    if (!periodValid) return;
    // リクエスト開始時の期間を捕捉し、応答時に現在の選択と一致するときだけ反映する（F-5）。
    const reqFrom = from;
    const reqTo = to;
    const isStale = () =>
      periodRef.current.from !== reqFrom || periodRef.current.to !== reqTo;

    setDigestLoading(true);
    setDigestError(null);
    try {
      const res = await namilogApi.generateDigest(reqFrom, reqTo, force);
      if (isStale()) return; // 期間が変わっていたら別期間の結果を上書きしない。
      setDigest(res);
    } catch (e) {
      if (isStale()) return; // 期間が変わっていたらエラーも出さない（新期間の状態を尊重）。
      // 既存流儀の優しい文言（デザイン6章のトーン）。状態コードで軽く出し分ける。
      let msg = "うまくまとめられなかったよ。少し待って、もう一度試してね。";
      if (e instanceof ApiError) {
        if (e.status === 422) {
          msg = "この期間ではまだまとめを作れないみたい。記録がたまってから、また試してね。";
        } else if (e.status === 503) {
          msg = "いまはまとめを作れないみたい。少し時間をおいて、また試してね。";
        }
      }
      setDigestError(msg);
    } finally {
      // 期間が変わっていない場合のみローディングを畳む（stale 応答は effect 側が既に false 化済み）。
      if (!isStale()) setDigestLoading(false);
    }
  }

  // イワシ太郎（1画面1箇所）: 生成中→生成前文言、結果あり→生成後文言、それ以外→振り返り文言。
  const iwashiMessage = digestLoading
    ? IWASHI.digestBefore
    : digest
      ? IWASHI.digestAfter
      : IWASHI.historyReview;

  return (
    <>
      <AppHeader title="詳細履歴" back />
      <main className="screen">
        <h1 className="screen-title">これまでの波</h1>

        <IwashiTaro message={iwashiMessage} />

        {/* ===== 期間選択（プリセット＋カスタム）。波グラフ・一覧・ダイジェストが連動 ===== */}
        <div className="card">
          <h2 className="card-title">期間を選ぶ</h2>
          <div className="period-presets" role="group" aria-label="期間プリセット">
            {PRESETS.map((p) => (
              <button
                key={p.days}
                type="button"
                className={`period-preset-btn${presetDays === p.days ? " selected" : ""}`}
                aria-pressed={presetDays === p.days}
                onClick={() => selectPreset(p.days)}
              >
                {p.label}
              </button>
            ))}
            <button
              type="button"
              className={`period-preset-btn${presetDays === "custom" ? " selected" : ""}`}
              aria-pressed={presetDays === "custom"}
              onClick={() => setPresetDays("custom")}
            >
              期間を指定
            </button>
          </div>

          {presetDays === "custom" && (
            <div className="period-custom">
              <div className="manual-field">
                <label className="field-label" htmlFor="digest-from">
                  はじめ
                </label>
                <input
                  id="digest-from"
                  className="manual-input"
                  type="date"
                  max={today}
                  value={from}
                  onChange={(e) => setFrom(e.target.value)}
                />
              </div>
              <div className="manual-field">
                <label className="field-label" htmlFor="digest-to">
                  おわり
                </label>
                <input
                  id="digest-to"
                  className="manual-input"
                  type="date"
                  max={today}
                  value={to}
                  onChange={(e) => setTo(e.target.value)}
                />
              </div>
            </div>
          )}

          <p className="period-range-label" aria-live="polite">
            {formatShortDate(from)} 〜 {formatShortDate(to)}（{span}日間）
          </p>
          {presetDays === "custom" && !periodValid && (
            <p className="field-hint">
              {from > to
                ? "「はじめ」は「おわり」より前の日にしてね。"
                : to > today
                  ? "未来の日付は選べないよ。"
                  : `期間は最大${DIGEST_MAX_DAYS}日までだよ。`}
            </p>
          )}
        </div>

        {error && (
          <p className="error-note" role="alert">
            {error}
          </p>
        )}

        {loading ? (
          <div className="card" aria-busy="true">
            <p className="empty-note">読み込み中…</p>
          </div>
        ) : (
          <>
            <div className="card">
              <h2 className="card-title">スコア推移</h2>
              {hasSeries ? (
                <>
                  <WaveChart series={series} />
                  <div className="legend-row" aria-hidden="true">
                    <div className="legend-item">
                      <span className="legend-line" />
                      実測
                    </div>
                    <div className="legend-item">
                      <span className="legend-line dash" />
                      予測
                    </div>
                  </div>
                </>
              ) : (
                <p className="empty-note">
                  この期間には波を描くための記録がないよ。体調入力から少しずつためていこうね。
                </p>
              )}
            </div>

            <div className="card">
              <h2 className="card-title">一覧</h2>
              {listRows.length > 0 ? (
                listRows.map((r) => (
                  <div className="history-row" key={r.date}>
                    <div className="history-date">{formatShortDate(r.date)}</div>
                    <div className="history-scores">
                      {r.actual_score != null && (
                        <span className="mini-score">実 {r.actual_score}</span>
                      )}
                      {r.predicted_score != null && (
                        <span className="mini-score predict">
                          予 {r.predicted_score}
                        </span>
                      )}
                    </div>
                    <div className="history-comment">
                      {r.comment && r.comment.trim() !== ""
                        ? r.comment
                        : "（コメントなし）"}
                    </div>
                    {/* 当日分だけ、記録の差し替え（修正）へ入れる導線を出す（機能B。当日限定）。 */}
                    {r.date === today && (
                      <Link className="history-edit" href="/record">
                        修正する
                      </Link>
                    )}
                  </div>
                ))
              ) : (
                <p className="empty-note">この期間にはまだ記録がないよ。</p>
              )}
            </div>

            {/* ===== 期間ダイジェスト（NL-API-19） ===== */}
            <div className="card">
              <h2 className="card-title">この期間のダイジェスト</h2>

              {digestLoading ? (
                // 生成中: やさしいローディング（イワシ太郎の生成前文言は画面上部で表示中）。
                <GentleLoader
                  base="この期間の記録をまとめているよ…"
                  waking="もう少しだけ、まとめているよ…"
                />
              ) : digest ? (
                <>
                  <DigestCard digest={digest} />
                  <button
                    className="btn btn-secondary btn-block"
                    onClick={() => makeDigest(true)}
                    style={{ marginTop: 16 }}
                  >
                    もう一度まとめる
                  </button>
                </>
              ) : (
                <>
                  <p className="field-hint" style={{ marginBottom: 12 }}>
                    選んだ期間の記録を、イワシ太郎がやさしくまとめるよ。
                  </p>
                  <button
                    className="btn btn-primary btn-block"
                    onClick={() => makeDigest(false)}
                    disabled={!periodValid || !hasActualInPeriod}
                  >
                    ダイジェストを作る
                  </button>
                  {!hasActualInPeriod && (
                    <p className="field-hint" style={{ marginTop: 8 }}>
                      この期間には実測の記録がないよ。記録がたまると、まとめを作れるようになるね。
                    </p>
                  )}
                </>
              )}

              {digestError && (
                <p className="error-note" role="alert" style={{ marginTop: 12 }}>
                  {digestError}
                </p>
              )}
            </div>
          </>
        )}
      </main>
    </>
  );
}

// ダイジェストカード本体（スマホ1画面程度）。3セクション: 体調ダイジェスト／良かった日／悪かった日。
function DigestCard({ digest }: { digest: DigestResponse }) {
  return (
    <div>
      <div className="digest-section">
        <h3>体調ダイジェスト</h3>
        <p className="digest-summary">{digest.summary}</p>
      </div>

      <div className="digest-section">
        <h3>調子の良かった日と対処</h3>
        {digest.good_days.length > 0 ? (
          digest.good_days.map((d, i) => <DigestDayItem key={`g-${i}`} day={d} />)
        ) : (
          <p className="digest-empty">この期間で特に目立った日は見つからなかったよ。</p>
        )}
      </div>

      <div className="digest-section">
        <h3>調子の悪かった日と対処</h3>
        {digest.bad_days.length > 0 ? (
          digest.bad_days.map((d, i) => <DigestDayItem key={`b-${i}`} day={d} />)
        ) : (
          <p className="digest-empty">この期間で特に目立った日は見つからなかったよ。</p>
        )}
      </div>
    </div>
  );
}

function DigestDayItem({ day }: { day: { date: string; note: string; coping: string } }) {
  // 日付は不正な文字列でも formatShortDate が原文フォールバックするため安全。
  return (
    <div className="digest-day">
      <p className="d">{formatShortDate(day.date)}</p>
      {day.note && <p className="note">{day.note}</p>}
      {day.coping && (
        <p className="coping">
          <span className="k">対処:</span> {day.coping}
        </p>
      )}
    </div>
  );
}
