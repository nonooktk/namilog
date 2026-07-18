// ホーム先行取得キャッシュの単体テスト。
// - prefetchHome は重複起動しない。
// - consumeHome は先行取得があればそれを返し、なければ新規取得する（一度きり）。
// - clearPrefetchedHome / TTL 超過で先行取得を破棄する。

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// namilogApi.getHome だけをモックする（api.ts の他の依存を引き込まない）。
const getHome = vi.fn();
vi.mock("./api", () => ({ namilogApi: { getHome: () => getHome() } }));

import { prefetchHome, consumeHome, clearPrefetchedHome } from "./prefetch";

describe("prefetch（ホーム先行取得）", () => {
  beforeEach(() => {
    getHome.mockReset();
    clearPrefetchedHome();
    vi.useRealTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("prefetchHome は重複起動しない", () => {
    getHome.mockResolvedValue({ ok: 1 });
    prefetchHome();
    prefetchHome();
    expect(getHome).toHaveBeenCalledTimes(1);
  });

  it("consumeHome は先行取得の結果をそのまま返す（新規取得しない）", async () => {
    const payload = { today: {} };
    getHome.mockResolvedValue(payload);
    prefetchHome();
    const result = await consumeHome();
    expect(result).toBe(payload);
    expect(getHome).toHaveBeenCalledTimes(1); // 先行の1回のみ
  });

  it("先行取得が無ければ consumeHome が新規取得する", async () => {
    const payload = { today: {} };
    getHome.mockResolvedValue(payload);
    const result = await consumeHome();
    expect(result).toBe(payload);
    expect(getHome).toHaveBeenCalledTimes(1);
  });

  it("consumeHome は一度きり（消費後は次回に新規取得する）", async () => {
    getHome.mockResolvedValue({ today: {} });
    prefetchHome();
    await consumeHome(); // 先行分を消費（呼び出し1回目）
    await consumeHome(); // 新規取得（呼び出し2回目）
    expect(getHome).toHaveBeenCalledTimes(2);
  });

  it("clearPrefetchedHome 後の consumeHome は新規取得する", async () => {
    getHome.mockResolvedValue({ today: {} });
    prefetchHome();
    clearPrefetchedHome();
    await consumeHome();
    // 先行の1回 + 消費時の新規1回 = 2回
    expect(getHome).toHaveBeenCalledTimes(2);
  });

  it("TTL 超過の先行取得は使わず新規取得する", async () => {
    vi.useFakeTimers();
    getHome.mockResolvedValue({ today: {} });
    prefetchHome();
    vi.advanceTimersByTime(31_000); // TTL(30s) 超過
    await consumeHome();
    // 先行の1回 + TTL 超過による新規1回 = 2回
    expect(getHome).toHaveBeenCalledTimes(2);
  });

  it("consumeHome は先行取得の reject を伝播する（消費側で握れる）", async () => {
    getHome.mockRejectedValue(new Error("api down"));
    prefetchHome();
    await expect(consumeHome()).rejects.toThrow("api down");
  });
});
