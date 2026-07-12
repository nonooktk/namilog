import type { SeriesPoint } from "@/lib/types";

// 波グラフ（デザイン仕様5.4）。実測=実線＋淡い面グラフ、予測=破線。
// 外部グラフライブラリは採用せず SVG を自前描画する。
//   理由: 描画要件が「1本の折れ線＋破線＋薄い面」と単純で、ライブラリ導入は
//   バンドル増・依存管理コストに見合わない。モックの波表現をそのまま再現でき、
//   色相もデザイン2.4（赤緑不使用）に完全準拠できるため。
// スコアは 1〜10 の固定スケールで縦軸に写像する。

const W = 320;
const H = 150;
const PAD_X = 8;
const TOP = 12; // score 10 の y
const BOTTOM = 132; // score 1 の y

function yFor(score: number): number {
  const clamped = Math.max(1, Math.min(10, score));
  return TOP + ((10 - clamped) / 9) * (BOTTOM - TOP);
}

function xFor(index: number, count: number): number {
  if (count <= 1) return W / 2;
  return PAD_X + (index * (W - 2 * PAD_X)) / (count - 1);
}

function toPoints(
  series: SeriesPoint[],
  pick: (p: SeriesPoint) => number | null,
): string {
  const n = series.length;
  return series
    .map((p, i) => {
      const v = pick(p);
      if (v == null) return null;
      return `${xFor(i, n).toFixed(1)},${yFor(v).toFixed(1)}`;
    })
    .filter((s): s is string => s !== null)
    .join(" ");
}

export function WaveChart({ series }: { series: SeriesPoint[] }) {
  const n = series.length;
  const actualPts = toPoints(series, (p) => p.actual);
  const predictedPts = toPoints(series, (p) => p.predicted);

  // 面グラフ（実測ラインの下をふわっと塗る）。実測が2点以上あるときのみ。
  let areaPolygon: string | null = null;
  const actualIdx = series
    .map((p, i) => (p.actual != null ? i : -1))
    .filter((i) => i >= 0);
  if (actualIdx.length >= 2) {
    const firstX = xFor(actualIdx[0], n);
    const lastX = xFor(actualIdx[actualIdx.length - 1], n);
    areaPolygon = `${actualPts} ${lastX.toFixed(1)},${H} ${firstX.toFixed(1)},${H}`;
  }

  const actualVals = series
    .map((p) => p.actual)
    .filter((v): v is number => v != null);
  const summary =
    actualVals.length > 0
      ? `実測スコアは ${Math.min(...actualVals)} 点から ${Math.max(
          ...actualVals,
        )} 点の範囲で推移。`
      : "実測データはまだありません。";

  return (
    <svg
      className="waveform-svg"
      viewBox={`0 0 ${W} ${H}`}
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label={`スコア推移グラフ。実線が実測、破線が予測。${summary}`}
    >
      <defs>
        <linearGradient id="waveFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#E4D9F3" stopOpacity="0.8" />
          <stop offset="100%" stopColor="#E4D9F3" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* グリッド線（score 10 / 7 / 4 / 1 のあたり・最小限） */}
      {[10, 7, 4, 1].map((s) => (
        <line
          key={s}
          x1="0"
          y1={yFor(s)}
          x2={W}
          y2={yFor(s)}
          stroke="#EAE3F2"
          strokeWidth="1"
        />
      ))}

      {areaPolygon && <polygon points={areaPolygon} fill="url(#waveFill)" />}

      {predictedPts && (
        <polyline
          points={predictedPts}
          fill="none"
          stroke="#6B5490"
          strokeWidth="2"
          strokeDasharray="5 4"
          strokeLinecap="round"
        />
      )}
      {actualPts && (
        <polyline
          points={actualPts}
          fill="none"
          stroke="#6B5490"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      )}
    </svg>
  );
}
