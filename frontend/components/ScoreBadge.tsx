import { scoreBand, bandLabel } from "@/lib/score";

// スコアの円バッジ（デザイン仕様5.3）。
// - 背景色はスコア帯グラデーション（信号色は使わない）だが、色だけに依存させない。
// - 予測は破線の輪郭（predict）、実測は塗り。区別は色ではなく形状＋キャプション（呼び出し側）。
// - aria-label で「数値＋帯ラベル」を読み上げられるようにする（デザイン7章）。
export function ScoreBadge({
  score,
  predict = false,
  size = 88,
  label,
}: {
  score: number | null;
  predict?: boolean;
  size?: number;
  /** 読み上げ用の接頭辞（例:「本日の実測スコア」）。 */
  label: string;
}) {
  const numSize = Math.round(size * 0.36);
  const denSize = Math.max(10, Math.round(size * 0.135));

  if (score == null) {
    return (
      <div
        className="score-badge empty"
        style={{ width: size, height: size }}
        role="img"
        aria-label={`${label}はまだありません`}
      >
        <span className="num" style={{ fontSize: numSize * 0.7 }} aria-hidden="true">
          —
        </span>
      </div>
    );
  }

  const band = scoreBand(score);
  const cls = ["score-badge", band, predict ? "predict" : ""]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={cls}
      style={{ width: size, height: size }}
      role="img"
      aria-label={`${label} ${score}点、${bandLabel(score)}`}
    >
      <span className="num" style={{ fontSize: numSize }} aria-hidden="true">
        {score}
      </span>
      <span className="den" style={{ fontSize: denSize }} aria-hidden="true">
        /10
      </span>
    </div>
  );
}
