// ウォームアップ ping の単体テスト。
// - /health を1回だけ叩くこと。
// - fetch が reject/throw しても呼び出し元へ伝播しない（fire-and-forget）こと。

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// API_BASE を固定し、supabase クライアント等のグラフを引き込まないようにモックする。
vi.mock("./api", () => ({ API_BASE: "http://api.test" }));

import { warmUpApi } from "./warmup";

describe("warmUpApi", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("/health を GET で1回だけ叩く", () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);

    warmUpApi();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/health");
    expect(init).toMatchObject({ method: "GET", cache: "no-store" });
  });

  it("fetch が reject しても例外を投げない", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error("network"));
    vi.stubGlobal("fetch", fetchMock);

    expect(() => warmUpApi()).not.toThrow();
    // 未処理拒否が起きないことを確認するため、マイクロタスクを流す。
    await Promise.resolve();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("fetch が同期的に throw しても握りつぶす", () => {
    const fetchMock = vi.fn(() => {
      throw new Error("boom");
    });
    vi.stubGlobal("fetch", fetchMock);

    expect(() => warmUpApi()).not.toThrow();
  });
});
