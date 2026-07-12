"use client";

// ホーム（NL-API-05: GET /api/home）。
// 本日の実測/予測（アイコン＋文言で区別）、明日の予測＋一言対策（M2 は degrade 表示）、
// メニュー4枚。crisis_notice が true のとき相談窓口カードをやさしく表示する。

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { namilogApi } from "@/lib/api";
import { signOut } from "@/lib/supabase";
import type { HomeResponse } from "@/lib/types";
import { ScoreBadge } from "@/components/ScoreBadge";
import { SupportCard } from "@/components/SupportCard";
import { AppHeader } from "@/components/AppHeader";
import { bandLabel, todayMessage } from "@/lib/score";

function SignOutButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  async function handle() {
    setBusy(true);
    await signOut();
    router.replace("/login");
  }
  return (
    <button className="icon-btn" onClick={handle} disabled={busy} aria-label="ログアウト">
      ログアウト
    </button>
  );
}

export default function HomePage() {
  const [home, setHome] = useState<HomeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const data = (await namilogApi.getHome()) as HomeResponse;
        if (mounted) setHome(data);
      } catch {
        if (mounted) setError("情報を読み込めませんでした。通信状況を確認してね。");
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const actualScore = home?.today.actual?.actual_score ?? null;
  const todayPredScore = home?.today.prediction?.predicted_score ?? null;
  const labelScore = actualScore ?? todayPredScore;
  const tomorrow = home?.tomorrow.prediction ?? null;

  return (
    <>
      <AppHeader title="ホーム" right={<SignOutButton />} />
      <main className="screen">
        <h1 className="screen-title">おかえりなさい</h1>

        {loading && (
          <div className="card" aria-busy="true">
            <p className="empty-note">読み込み中…</p>
          </div>
        )}

        {error && (
          <p className="error-note" role="alert">
            {error}
          </p>
        )}

        {home && (
          <>
            <section className="today-card" aria-label="本日の様子">
              <h2 className="card-title" style={{ marginBottom: 14 }}>
                本日の様子
              </h2>
              <div className="score-row">
                <div className="score-badge-wrap">
                  <ScoreBadge score={actualScore} label="本日の実測スコア" />
                  <div className="score-caption">
                    <span className="type">
                      <span className="dot-solid" aria-hidden="true" />
                      実測
                    </span>
                  </div>
                </div>
                <div className="score-badge-wrap">
                  <ScoreBadge
                    score={todayPredScore}
                    predict
                    label="本日の予測スコア"
                  />
                  <div className="score-caption">
                    <span className="type">
                      <span className="dot-dash" aria-hidden="true" />
                      予測
                    </span>
                  </div>
                </div>
              </div>

              {labelScore != null ? (
                <div className="score-label">{todayMessage(labelScore)}</div>
              ) : (
                <div className="score-label">
                  今日の記録はこれから。体調入力からはじめてみてね
                </div>
              )}

              {/* 明日の予測。M2 は予測未生成のため degrade 表示（§7.5）。 */}
              <div className="tomorrow-block">
                {tomorrow ? (
                  <>
                    <div className="tomorrow-head">
                      <ScoreBadge
                        score={tomorrow.predicted_score}
                        predict
                        size={56}
                        label="明日の予測スコア"
                      />
                      <div>
                        <div style={{ fontSize: 14, color: "var(--color-text)" }}>
                          明日の予測
                        </div>
                        <div style={{ fontSize: 14, fontWeight: 700 }}>
                          {bandLabel(tomorrow.predicted_score)}
                        </div>
                      </div>
                    </div>
                    <div className="advice-bubble">
                      <span aria-hidden="true">💭</span>
                      <span>{tomorrow.advice}</span>
                    </div>
                  </>
                ) : (
                  <>
                    <div style={{ fontSize: 14, fontWeight: 700 }}>明日の予測</div>
                    <p className="degrade-note">
                      {home.notice ??
                        "明日の予測はまだ準備中だよ。数日ぶんの記録がたまると、そっとお知らせできるようになるね。"}
                    </p>
                  </>
                )}
              </div>
            </section>

            {home.crisis_notice && <SupportCard />}

            <nav className="menu-grid" aria-label="メニュー">
              <Link className="menu-item" href="/record">
                <span className="icon" aria-hidden="true">
                  📝
                </span>
                <span className="label">体調入力</span>
              </Link>
              <Link className="menu-item" href="/history">
                <span className="icon" aria-hidden="true">
                  📈
                </span>
                <span className="label">詳細履歴</span>
              </Link>
              <Link className="menu-item" href="/factors">
                <span className="icon" aria-hidden="true">
                  🌤️
                </span>
                <span className="label">外部情報選択</span>
              </Link>
              {/* フィードバックチャット（M3 で導線接続）。 */}
              <Link className="menu-item" href="/feedback">
                <span className="icon" aria-hidden="true">
                  💬
                </span>
                <span className="label">
                  フィードバック
                  <br />
                  チャット
                </span>
              </Link>
            </nav>
          </>
        )}
      </main>
    </>
  );
}
