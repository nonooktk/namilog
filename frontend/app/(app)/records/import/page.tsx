"use client";

// 過去ログの後追い一括登録（機能A）。
// オンボーディングを終えたあとでも、手元の過去ログをいつでもまとめて取り込めるようにする画面。
//
// - 入力 UI・パース・検証はオンボーディング Step2 と同じ共通コンポーネント（BulkRecordEntry）を使う。
// - 登録は既存の POST /api/records/bulk（namilogApi.bulkRecords）を再利用する（新 API は作らない）。
// - 既存日付の記録は UPSERT で上書きされるため、登録前に注意書きで明示する（仕様書 4.1）。
// - この画面は (app) ルートグループ配下なので RequireAuth / OnboardingGate の内側にあり、
//   認証済み・オンボーディング完了ユーザーだけが到達する。

import { useState } from "react";
import { useRouter } from "next/navigation";
import { namilogApi } from "@/lib/api";
import { AppHeader } from "@/components/AppHeader";
import { BulkRecordEntry } from "@/components/BulkRecordEntry";
import type { ParsedRecord } from "@/lib/records-import";

export default function RecordsImportPage() {
  const router = useRouter();
  const [records, setRecords] = useState<ParsedRecord[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedCount, setSavedCount] = useState<number | null>(null);

  async function handleSave() {
    if (records.length === 0) return;
    setBusy(true);
    setError(null);
    setSavedCount(null);
    try {
      const res = (await namilogApi.bulkRecords(records)) as { saved: number };
      setSavedCount(res?.saved ?? records.length);
      // 保存済みの控えは共通コンポーネント側の入力に残るが、再送は同一 UPSERT のため無害。
    } catch {
      setError(
        "記録を保存できませんでした。通信状況を確認して、もう一度試してね。",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <AppHeader title="過去の記録を追加" back />
      <main className="screen">
        <h1 className="screen-title">過去の記録を追加</h1>
        <p className="step-lead">
          あとから見つかった過去の記録も、ここからいつでもまとめて取り込めるよ。
          「日付,スコア,コメント」の形で貼り付けるか、1件ずつ入力してね。
        </p>

        {/* UPSERT（上書き）の明示。既存日付は最新の内容で置き換わることを登録前に伝える。 */}
        <p className="error-note" role="note">
          すでに記録がある日付を含めると、その日の内容は今回の入力で
          <strong>上書き</strong>されるよ。残したい記録は消えないように気をつけてね。
        </p>

        {savedCount != null && (
          <p className="toast" role="status">
            {savedCount}件の記録を保存したよ。教えてくれてありがとう。
          </p>
        )}
        {error && (
          <p className="error-note" role="alert">
            {error}
          </p>
        )}

        <div className="card">
          {/* 入力 UI・パース・検証はオンボーディング Step2 と共通（BulkRecordEntry）。 */}
          <BulkRecordEntry onRecordsChange={setRecords} disabled={busy} />
        </div>

        <button
          className="btn btn-primary btn-block"
          onClick={handleSave}
          disabled={records.length === 0 || busy}
        >
          {busy
            ? "保存中…"
            : records.length > 0
              ? `${records.length}件を保存する`
              : "記録を入力してね"}
        </button>
        <div style={{ height: 12 }} />
        <button
          className="btn btn-secondary btn-block"
          onClick={() => router.push("/")}
          disabled={busy}
        >
          ホームに戻る
        </button>
      </main>
    </>
  );
}
