// こころの整理（MI セッション）初期表示ロジックの単体テスト。
// レビュー必須対応（2026-07-19_MI_Task2レビュー）: session.status を確認せず chatting に入れる穴の回帰防止。

import { describe, it, expect } from "vitest";
import { resolveInitialView, MI_BOUNDARY_TURN } from "./mi";
import type { MiSession, MiStatus } from "./types";

// テスト用の MiSession を組み立てる。status / turn_count / last_summary のみ差し替える。
function makeSession(overrides: Partial<MiSession> = {}): MiSession {
  return {
    id: "s1",
    user_id: "u1",
    theme: null,
    status: "active",
    state: {},
    turn_count: 0,
    crisis_flag: false,
    last_summary: null,
    created_at: "2026-07-19T00:00:00Z",
    updated_at: "2026-07-19T00:00:00Z",
    ...overrides,
  };
}

describe("resolveInitialView", () => {
  it("session=null かつ安全フラグなし → intro（開始導線）", () => {
    expect(resolveInitialView(null, false)).toEqual({ phase: "intro" });
  });

  it("session=null かつ安全フラグあり → halted（危機の窓口案内を再読込でも維持）", () => {
    // 現行バックエンドは halted を session=null で返すため、フラグで復元するのが要。
    expect(resolveInitialView(null, true)).toEqual({ phase: "halted" });
  });

  it("status=active → chatting。turn_count が境界未満なら boundary=false", () => {
    const view = resolveInitialView(
      makeSession({ status: "active", turn_count: MI_BOUNDARY_TURN - 1 }),
      false,
    );
    expect(view).toEqual({ phase: "chatting", boundary: false });
  });

  it("status=active かつ turn_count が境界以上なら boundary=true", () => {
    const view = resolveInitialView(
      makeSession({ status: "active", turn_count: MI_BOUNDARY_TURN }),
      false,
    );
    expect(view).toEqual({ phase: "chatting", boundary: true });
  });

  it("status=halted → halted（防御。将来 API が halted を返す場合でも入力を復活させない）", () => {
    expect(resolveInitialView(makeSession({ status: "halted" }), false)).toEqual({
      phase: "halted",
    });
  });

  it("status=active でも安全フラグが残っていれば halted を優先（安全側）", () => {
    expect(resolveInitialView(makeSession({ status: "active" }), true)).toEqual({
      phase: "halted",
    });
  });

  it("status=closed → closed。last_summary を要約として渡す", () => {
    const view = resolveInitialView(
      makeSession({ status: "closed", last_summary: "今回のまとめ" }),
      false,
    );
    expect(view).toEqual({ phase: "closed", summary: "今回のまとめ" });
  });

  it("未知の status → intro（対話に入れずフェイルセーフ安全側）", () => {
    // 契約外の値が来ても chatting へは絶対に入れない。
    const view = resolveInitialView(
      makeSession({ status: "unknown" as MiStatus }),
      false,
    );
    expect(view).toEqual({ phase: "intro" });
  });
});
