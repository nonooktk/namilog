import Link from "next/link";
import type { ReactNode } from "react";

// 画面上部の共通ヘッダ。戻る導線（ホームへ）とタイトル、右側の任意アクションを持つ。
export function AppHeader({
  title,
  back = false,
  right,
}: {
  title: string;
  back?: boolean;
  right?: ReactNode;
}) {
  return (
    <header className="app-header">
      {back ? (
        <Link className="icon-btn" href="/" aria-label="ホームに戻る">
          <span aria-hidden="true">‹</span>
          <span>ホーム</span>
        </Link>
      ) : (
        <span className="app-title">なみログ</span>
      )}
      <span className="spacer" />
      <span className="app-title" aria-hidden={back ? undefined : true}>
        {title}
      </span>
      {right}
    </header>
  );
}
