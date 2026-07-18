// こころの整理（MI セッション）のフロント側純粋ロジック。
// 画面（app/(app)/mi/page.tsx）から分離してユニットテスト可能にする。
//
// レビュー必須対応（2026-07-19_MI_Task2レビュー）:
//  初期ロードで GET /api/mi/session の session.status を確認せず一律 chatting に入れていた穴を塞ぐ。
//  status が 'active' 以外のセッションは対話に入れず、安全側の UI（危機なら halted・終了なら closed）へ倒す。

import type { MiSession } from "./types";

// バックエンド定数のミラー（乖離時はバグ源。将来 API 返却で single-source 化を検討）。
export const MI_BOUNDARY_TURN = 15; // mi_session.BOUNDARY_TURN と一致。

// 危機で中断（halted）した痕跡を残す sessionStorage キー。
// 保存するのは「安全上の理由で中断した」ブール相当のみ。発話・逐語などの機微情報は一切保存しない。
// sessionStorage はタブを閉じれば消えるため、共有端末での残存リスクを抑えつつ再読込耐性を得る。
export const MI_SAFETY_KEY = "namilog_mi_safety_halted";

// 初期表示フェーズの決定結果。
export type MiInitialView =
  | { phase: "chatting"; boundary: boolean }
  | { phase: "halted" }
  | { phase: "closed"; summary: string | null }
  | { phase: "intro" };

/**
 * 初期ロード時の表示フェーズを安全側に決める。
 *
 * - session が null: 現行バックエンドは active のみ返すため、halted / closed はここに落ちる。
 *   直前に危機中断していれば（safetyFlag=true）、再読込でも窓口案内（halted）を消さない。
 * - session.status === 'active': 通常の対話（chatting）。境界は turn_count から推定。
 * - session.status === 'halted': 危機中断。窓口案内・入力なし（防御。将来 API が halted を返す場合に備える）。
 * - session.status === 'closed': 区切り済み（まとめ表示）。
 * - それ以外（未知の status）: 対話に入れず intro（開始導線）へ倒す＝フェイルセーフ安全側。
 */
export function resolveInitialView(
  session: MiSession | null,
  safetyFlag: boolean,
): MiInitialView {
  if (!session) {
    return safetyFlag ? { phase: "halted" } : { phase: "intro" };
  }
  switch (session.status) {
    case "active":
      // active でも安全フラグが残っていれば安全側（halted）を優先する。
      if (safetyFlag) return { phase: "halted" };
      return {
        phase: "chatting",
        boundary: session.turn_count >= MI_BOUNDARY_TURN,
      };
    case "halted":
      return { phase: "halted" };
    case "closed":
      return { phase: "closed", summary: session.last_summary };
    default:
      return { phase: "intro" };
  }
}
