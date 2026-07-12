// 医療免責の常設バー（デザイン仕様5.7 / 6.4）。各画面のフッターに常時掲示する。
export function DisclaimerBar() {
  return (
    <p className="disclaimer-bar" role="note">
      なみログは、体調の記録と傾向の把握をお手伝いするアプリです。医師による診断や治療の代わりになるものではありません。体調に不安があるときは、医療機関にご相談ください。
    </p>
  );
}
