// ホーム先行取得キャッシュの単体テスト。
// - prefetchHome は（同一ユーザーで）重複起動しない。
// - consumeHome は現ユーザーの先行取得があればそれを返し、なければ新規取得する（一度きり）。
// - セッション分離: 別ユーザーの先行取得は再利用せず、必ず新規取得する。
// - clearPrefetchedHome / TTL 超過で先行取得を破棄する。

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// namilogApi.getHome だけをモックする（api.ts の他の依存を引き込まない）。
const getHome = vi.fn();
vi.mock("./api", () => ({ namilogApi: { getHome: () => getHome() } }));

import { prefetchHome, consumeHome, clearPrefetchedHome } from "./prefetch";

// テスト用のユーザーID。
const USER_A = "user-a";
const USER_B = "user-b";

describe("prefetch（ホーム先行取得）", () => {
  beforeEach(() => {
    getHome.mockReset();
    clearPrefetchedHome();
    vi.useRealTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("prefetchHome は同一ユーザーで重複起動しない", () => {
    getHome.mockResolvedValue({ ok: 1 });
    prefetchHome(USER_A);
    prefetchHome(USER_A);
    expect(getHome).toHaveBeenCalledTimes(1);
  });

  it("consumeHome は同一ユーザーの先行取得をそのまま返す（新規取得しない）", async () => {
    const payload = { today: {} };
    getHome.mockResolvedValue(payload);
    prefetchHome(USER_A);
    const result = await consumeHome(USER_A);
    expect(result).toBe(payload);
    expect(getHome).toHaveBeenCalledTimes(1); // 先行の1回のみ
  });

  it("先行取得が無ければ consumeHome が新規取得する", async () => {
    const payload = { today: {} };
    getHome.mockResolvedValue(payload);
    const result = await consumeHome(USER_A);
    expect(result).toBe(payload);
    expect(getHome).toHaveBeenCalledTimes(1);
  });

  it("consumeHome は一度きり（消費後は次回に新規取得する）", async () => {
    getHome.mockResolvedValue({ today: {} });
    prefetchHome(USER_A);
    await consumeHome(USER_A); // 先行分を消費（呼び出し1回目）
    await consumeHome(USER_A); // 新規取得（呼び出し2回目）
    expect(getHome).toHaveBeenCalledTimes(2);
  });

  // --- セッション分離（必須指摘の対応） ---

  it("別ユーザーの consumeHome は先行取得を再利用せず新規取得する", async () => {
    const payloadA = { user: "A" };
    getHome.mockResolvedValue(payloadA);
    prefetchHome(USER_A); // A が先行取得（呼び出し1回目）
    getHome.mockResolvedValue({ user: "B" });
    const result = await consumeHome(USER_B); // B が消費 → A の結果は使わない
    expect(result).toEqual({ user: "B" }); // 新規取得（呼び出し2回目）
    expect(result).not.toBe(payloadA);
    expect(getHome).toHaveBeenCalledTimes(2);
  });

  it("別ユーザーの prefetchHome は前ユーザーのキャッシュを破棄して起動する", async () => {
    getHome.mockResolvedValue({ today: {} });
    prefetchHome(USER_A); // 呼び出し1回目
    prefetchHome(USER_B); // 別ユーザー → 破棄して再起動（呼び出し2回目）
    expect(getHome).toHaveBeenCalledTimes(2);
    // 残っているのは B のキャッシュ。A で消費しても再利用されない（新規取得）。
    await consumeHome(USER_A); // 呼び出し3回目
    expect(getHome).toHaveBeenCalledTimes(3);
  });

  it("clearPrefetchedHome（ログアウト相当）後の consumeHome は新規取得する", async () => {
    getHome.mockResolvedValue({ today: {} });
    prefetchHome(USER_A);
    clearPrefetchedHome(); // ログアウト等でキャッシュを破棄
    await consumeHome(USER_A);
    // 先行の1回 + 消費時の新規1回 = 2回
    expect(getHome).toHaveBeenCalledTimes(2);
  });

  it("clearPrefetchedHome 後に別ユーザーが consumeHome しても前ユーザーの結果を返さない", async () => {
    const payloadA = { user: "A" };
    getHome.mockResolvedValue(payloadA);
    prefetchHome(USER_A);
    clearPrefetchedHome(); // A のログアウト
    getHome.mockResolvedValue({ user: "B" });
    const result = await consumeHome(USER_B);
    expect(result).toEqual({ user: "B" });
    expect(result).not.toBe(payloadA);
  });

  // --- TTL / 例外 ---

  it("TTL 超過の先行取得は使わず新規取得する", async () => {
    vi.useFakeTimers();
    getHome.mockResolvedValue({ today: {} });
    prefetchHome(USER_A);
    vi.advanceTimersByTime(31_000); // TTL(30s) 超過
    await consumeHome(USER_A);
    // 先行の1回 + TTL 超過による新規1回 = 2回
    expect(getHome).toHaveBeenCalledTimes(2);
  });

  it("TTL 超過キャッシュは次の prefetchHome で破棄されて再起動する", async () => {
    vi.useFakeTimers();
    getHome.mockResolvedValue({ today: {} });
    prefetchHome(USER_A); // 呼び出し1回目
    vi.advanceTimersByTime(31_000); // TTL 超過
    prefetchHome(USER_A); // 期限切れを破棄して再起動（呼び出し2回目）
    expect(getHome).toHaveBeenCalledTimes(2);
  });

  it("consumeHome は先行取得の reject を伝播する（消費側で握れる）", async () => {
    getHome.mockRejectedValue(new Error("api down"));
    prefetchHome(USER_A);
    await expect(consumeHome(USER_A)).rejects.toThrow("api down");
  });
});
