"use client";

// 詳細履歴（NL-API-10: GET /api/history/series、NL-API-09: GET /api/records）。
// 波グラフ（実測=実線・予測=破線・SVG 自前描画）を先に見せ、その下に日付・スコア・コメントの一覧。
// 直近30日を既定範囲とする。

import { useEffect, useState } from "react";
import { namilogApi } from "@/lib/api";
import type {
  ListRecordsResponse,
  SeriesResponse,
  SeriesPoint,
  HistoryRow,
} from "@/lib/types";
import { AppHeader } from "@/components/AppHeader";
import { WaveChart } from "@/components/WaveChart";
import { formatShortDate, isoDaysAgo, todayISO } from "@/lib/date";

export default function HistoryPage() {
  const [series, setSeries] = useState<SeriesPoint[]>([]);
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      const from = isoDaysAgo(30);
      const to = todayISO();
      try {
        const [s, r] = await Promise.all([
          namilogApi.getSeries(from, to) as Promise<SeriesResponse>,
          namilogApi.listRecords(from, to) as Promise<ListRecordsResponse>,
        ]);
        if (!mounted) return;
        setSeries(s.series ?? []);
        setRows(r.records ?? []);
      } catch {
        if (mounted) setError("履歴を読み込めませんでした。通信状況を確認してね。");
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const hasSeries = series.some(
    (p) => p.actual != null || p.predicted != null,
  );
  // 実測のある行のみ一覧に出す（予測だけの未来日行は履歴一覧に混ぜない）。
  const listRows = rows.filter((r) => r.actual_score != null);

  return (
    <>
      <AppHeader title="詳細履歴" back />
      <main className="screen">
        <h1 className="screen-title">これまでの波</h1>

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
                  まだ波を描くための記録がないよ。体調入力から少しずつためていこうね。
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
                  </div>
                ))
              ) : (
                <p className="empty-note">まだ記録がないよ。</p>
              )}
            </div>
          </>
        )}
      </main>
    </>
  );
}
