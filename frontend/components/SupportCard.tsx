// 相談窓口の案内カード（デザイン仕様5.7 / 6.5）。
// crisis_notice が true のときだけ、責めない・寄り添うトーンで表示する。
// 掲載窓口・電話番号は M4 までにシナモロール・キャタピーと最終確認する仮置き（デザイン6.5）。
export function SupportCard() {
  return (
    <section className="support-card" role="note" aria-label="相談窓口の案内">
      <span className="tag">ひとりで抱えないでね</span>
      <p>
        もし今、つらい気持ちが大きくなっているなら、ひとりで抱えなくて大丈夫。よかったら話してみてね。
      </p>
      <div className="contact">
        よりそいホットライン: 0120-279-338（24時間・無料）
        <br />
        こころの健康相談統一ダイヤル: 0570-064-556
      </div>
    </section>
  );
}
