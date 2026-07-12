"use client";

// 外部情報選択（NL-API-03: GET catalog、NL-API-11: GET selection、NL-API-12: PUT selection）。
// 12候補チップから3つ選択（ちょうど3件バリデーション）。AI 入れ替え提案枠は M3 のためプレースホルダー。

import { useEffect, useMemo, useState } from "react";
import { namilogApi } from "@/lib/api";
import type { CatalogResponse, CatalogItem, SelectionResponse } from "@/lib/types";
import { AppHeader } from "@/components/AppHeader";

const MAX = 3;

export default function FactorsPage() {
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [initial, setInitial] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const [cat, sel] = await Promise.all([
          namilogApi.getCatalog() as Promise<CatalogResponse>,
          namilogApi.getSelection() as Promise<SelectionResponse>,
        ]);
        if (!mounted) return;
        setCatalog(cat.catalog ?? []);
        const active = (sel.active ?? []).map((a) => a.factor_key);
        setSelected(active);
        setInitial(active);
      } catch {
        if (mounted) setError("候補を読み込めませんでした。通信状況を確認してね。");
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  function toggle(key: string) {
    setSaved(false);
    setSelected((prev) => {
      if (prev.includes(key)) return prev.filter((k) => k !== key);
      if (prev.length >= MAX) return prev; // 3件を超えて選べない
      return [...prev, key];
    });
  }

  const changed = useMemo(() => {
    if (selected.length !== initial.length) return true;
    const a = [...selected].sort();
    const b = [...initial].sort();
    return a.some((k, i) => k !== b[i]);
  }, [selected, initial]);

  const canSave = selected.length === MAX && changed && !saving;

  async function handleSave() {
    if (selected.length !== MAX) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const res = (await namilogApi.putSelection(selected)) as SelectionResponse;
      const active = (res.active ?? []).map((a) => a.factor_key);
      setSelected(active);
      setInitial(active);
      setSaved(true);
    } catch {
      setError("保存できませんでした。3つ選んでいるか確認して、もう一度試してね。");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <AppHeader title="外部情報選択" back />
      <main className="screen">
        <h1 className="screen-title">予測に使う情報</h1>
        <p
          className="field-hint"
          style={{ marginTop: -6, marginBottom: 12, lineHeight: 1.6 }}
        >
          12個の候補から、予測に使いたいものを3つ選んでね。後からいつでも変えられるよ。
        </p>

        {saved && <p className="toast" role="status">選んだ情報を保存したよ。</p>}
        {error && (
          <p className="error-note" role="alert">
            {error}
          </p>
        )}

        {loading ? (
          <div className="card" aria-busy="true">
            <p className="empty-note">読み込み中…</p>
          </div>
        ) : (
          <>
            <div
              className={`selection-count${selected.length > MAX ? " over" : ""}`}
              aria-live="polite"
            >
              選択中: {selected.length} / {MAX}
            </div>

            <div className="chip-grid" role="group" aria-label="予測に使う情報の候補">
              {catalog.map((c) => {
                const isSel = selected.includes(c.factor_key);
                const disabled = !isSel && selected.length >= MAX;
                return (
                  <button
                    key={c.factor_key}
                    type="button"
                    className={`chip${isSel ? " selected" : ""}`}
                    aria-pressed={isSel}
                    disabled={disabled}
                    onClick={() => toggle(c.factor_key)}
                  >
                    {c.label}
                  </button>
                );
              })}
            </div>

            <button
              className="btn btn-primary btn-block"
              onClick={handleSave}
              disabled={!canSave}
              style={{ marginBottom: 16 }}
            >
              {saving ? "保存中…" : "この3つで保存する"}
            </button>

            {/* AI 入れ替え提案は M3。枠だけ置き、優しい文言で準備中を伝える。 */}
            <section className="ai-suggest-card" aria-label="AIからの提案（準備中）">
              <span className="tag">AIからの提案</span>
              <p>ていあんは、もうすこしまってね。</p>
              <p style={{ color: "var(--color-text)" }}>
                記録がたまってくると、あなたの調子と関係していそうな情報を見つけて、そっと入れ替えを提案するよ。決めるのはいつもあなただからね。
              </p>
            </section>
          </>
        )}
      </main>
    </>
  );
}
