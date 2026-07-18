import { defineConfig } from "vitest/config";

// 最小構成（F-4）。フロントの純粋ロジック（lib 配下）だけを node 環境で実行する。
// DOM は不要なため jsdom 等は導入しない。
export default defineConfig({
  test: {
    environment: "node",
    include: ["lib/**/*.test.ts"],
  },
});
