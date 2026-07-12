"use client";

// 外部情報選択（NL-API-03: GET catalog、NL-API-11: GET selection、NL-API-12: PUT selection）。
// 12候補チップから3つ選択（ちょうど3件バリデーション）。
// AI 入れ替え提案（NL-API-13）: 提案の採否も「どれと入れ替えるか」も本人が選ぶ2段フロー（デザイン6.6・P2 是正）。

import { useEffect, useMemo, useState } from "react";
import { namilogApi } from "@/lib/api";
import type {
  CatalogResponse,
  CatalogItem,
  SelectionResponse,
  FactorSuggestResponse,
} from "@/lib/types";
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

  // AI 入れ替え提案（NL-API-13）。採否も「どれと入れ替えるか」も本人（デザイン6.6・P2 是正）。
  const [suggest, setSuggest] = useState<FactorSuggestResponse | null>(null);
  const [suggestDismissed, setSuggestDismissed] = useState(false);
  const [swapping, setSwapping] = useState(false);
  // 「入れ替える」押下後の「どれを外す？」選択モードと、本人が選んだ外す指標。
  const [choosingRemoval, setChoosingRemoval] = useState(false);
  const [removeKey, setRemoveKey] = useState<string | null>(null);

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

  // AI 提案は本体ロードと独立に取得（失敗しても選択機能は使える）。
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const s = await namilogApi.suggestFactor();
        if (mounted) setSuggest(s);
      } catch {
        // 提案は補助機能のため、取得失敗時は枠自体を出さない（握りつぶす）。
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const labelOf = useMemo(() => {
    const map = new Map(catalog.map((c) => [c.factor_key, c.label]));
    return (key: string) => map.get(key) ?? key;
  }, [catalog]);

  // 提案で「加える」指標。バックエンドは追加候補だけを返す（外す指標は本人が選ぶ）。
  const addKey = suggest?.suggested_key ?? null;
  // 外す候補＝現在アクティブな指標（万一 addKey が含まれていれば除外）。
  const removalCandidates = useMemo(
    () => initial.filter((k) => k !== addKey),
    [initial, addKey],
  );
  // アクティブが3件そろっている場合のみ「1つ外す」選択が必要（それ未満なら追加のみ）。
  const needsRemoval = removalCandidates.length >= MAX;

  // 「入れ替える」押下: 外す指標を選ぶ必要があれば選択モードへ、不要なら追加のみ適用。
  function beginSwap() {
    if (!addKey) return;
    if (needsRemoval) {
      setRemoveKey(null);
      setChoosingRemoval(true);
    } else {
      void applySwap(null);
    }
  }

  function cancelSwap() {
    setChoosingRemoval(false);
    setRemoveKey(null);
  }

  // 本人が選んだ removeKey を外し、提案キーを加えて selection を更新する（NL-API-12）。
  async function applySwap(remove: string | null) {
    if (!addKey) return;
    const base = remove ? removalCandidates.filter((k) => k !== remove) : removalCandidates;
    const next = [...base, addKey].slice(0, MAX);
    setSwapping(true);
    setError(null);
    setSaved(false);
    try {
      const res = (await namilogApi.putSelection(next)) as SelectionResponse;
      const active = (res.active ?? []).map((a) => a.factor_key);
      setSelected(active);
      setInitial(active);
      setSaved(true);
      setChoosingRemoval(false);
      setRemoveKey(null);
      setSuggestDismissed(true); // 反映済みの提案は畳む。
    } catch {
      setError("入れ替えできませんでした。少し待って、もう一度試してね。");
    } finally {
      setSwapping(false);
    }
  }

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

            {/* AI 入れ替え提案（NL-API-13）。採否も外す指標も決めるのは本人（デザイン6.6・P2 是正）。 */}
            {suggest && !suggestDismissed && (
              <section className="ai-suggest-card" aria-label="AIからの提案">
                <span className="tag">AIからの提案</span>
                {addKey ? (
                  !choosingRemoval ? (
                    /* 第1段階: 提案の理由を伝え、試すかどうかを本人が決める。 */
                    <>
                      <p>{suggest.reason}</p>
                      <p style={{ color: "var(--color-text)" }}>
                        {`「${suggest.suggested_label ?? labelOf(addKey)}」を試してみる？決めるのはいつもあなただからね。`}
                      </p>
                      <div className="ai-suggest-actions">
                        <button
                          type="button"
                          className="btn btn-secondary"
                          onClick={() => setSuggestDismissed(true)}
                          disabled={swapping}
                        >
                          今のままでいい
                        </button>
                        <button
                          type="button"
                          className="btn btn-primary"
                          onClick={beginSwap}
                          disabled={swapping}
                        >
                          {needsRemoval ? "入れ替える" : "追加する"}
                        </button>
                      </div>
                    </>
                  ) : (
                    /* 第2段階: 今の3つのうち「どれと入れ替えるか」を本人がチップで選ぶ。 */
                    <>
                      <p style={{ color: "var(--color-text)" }}>
                        {`「${suggest.suggested_label ?? labelOf(addKey)}」を使うために、いまの3つのうちどれと入れ替える？外したい情報を選んでね。`}
                      </p>
                      <div
                        className="chip-grid"
                        role="radiogroup"
                        aria-label="外す情報を選ぶ"
                        style={{ marginBottom: 8 }}
                      >
                        {removalCandidates.map((k) => {
                          const isSel = removeKey === k;
                          return (
                            <button
                              key={k}
                              type="button"
                              className={`chip${isSel ? " selected" : ""}`}
                              role="radio"
                              aria-checked={isSel}
                              disabled={swapping}
                              onClick={() => setRemoveKey(k)}
                            >
                              {labelOf(k)}
                            </button>
                          );
                        })}
                      </div>
                      <div className="ai-suggest-actions">
                        <button
                          type="button"
                          className="btn btn-secondary"
                          onClick={cancelSwap}
                          disabled={swapping}
                        >
                          やめる
                        </button>
                        <button
                          type="button"
                          className="btn btn-primary"
                          onClick={() => applySwap(removeKey)}
                          disabled={swapping || !removeKey}
                        >
                          {swapping
                            ? "入れ替え中…"
                            : removeKey
                              ? `「${labelOf(removeKey)}」と入れ替える`
                              : "入れ替える"}
                        </button>
                      </div>
                    </>
                  )
                ) : (
                  <>
                    <p>いまはていあんはないよ。</p>
                    <p style={{ color: "var(--color-text)" }}>
                      記録がたまってくると、あなたの調子と関係していそうな情報を見つけて、そっと入れ替えを提案するね。
                    </p>
                  </>
                )}
              </section>
            )}
          </>
        )}
      </main>
    </>
  );
}
