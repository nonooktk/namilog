# README_COMPETE — 記録管理機能（Claude / イーブイ 実装）

マルチモデルコンペ第1回。namilog「記録管理機能」の Claude エンジン実装です。
仕様書: `02_プロジェクト/namilog/設計/コンペ01_記録管理機能_共通実装仕様書.md`

## 実装サマリ

### 機能A：過去ログの後追い一括登録
- オンボーディングを終えたあとでも、いつでも過去ログをまとめて取り込める専用画面
  `/records/import`（`app/(app)/records/import/page.tsx`）を新設。
- 入力手段は CSV貼り付け／1件ずつ入力の両方。オンボーディング Step2 と**同一の入力 UI・パース・検証**を共有。
- 登録は既存 `POST /api/records/bulk`（`namilogApi.bulkRecords`）を再利用（新 API は追加していない）。
- 既存日付が UPSERT で上書きされる旨を、登録前に注意書き（`error-note` / `role="note"`）で明示。
- 導線：ホームのメニューに「過去の記録を追加」🗂️ を追加（`app/(app)/page.tsx`）。
- 保存失敗時はやさしい日本語メッセージ＋再試行導線（ボタンは押下可のまま残す）。

### 機能A：/onboarding 逆ガード
- オンボーディング完了済み（`profiles.onboarded_at != null`）が `/onboarding` に来たら、
  ウィザードを再表示せずホーム `/` へ送る逆ガードを `app/(onboarding)/onboarding/page.tsx` に追加。
- 既存の `OnboardingGate`（未完了→`/onboarding`）は無改変。逆方向のみ補う。
- 判定は `namilogApi.getProfile()` の `onboarded_at`。判定失敗時はウィザードを塞がない（degrade）。

### 機能B：当日記録のプリフィルと差し替え
- 体調入力 `/record`（`app/(app)/record/page.tsx`）を開いたとき、当日すでに記録があれば
  スコア・コメントをプリフィルし、「記録済み→差し替え」表示に切り替える
  （画面見出し・注意書き・保存ボタン文言・完了トーストで区別）。
- プリフィル用データは既存の `GET /api/records?from=today&to=today`（`namilogApi.listRecords`）を再利用。
  単日取得 API は追加していない。RLS 境界（`user_id` はトークンからサーバ側解決）は不変。
- 更新経路は既存どおり `POST /api/records`（同日 UPSERT）。予測突合（`_match_prediction`）と
  危機検知（`crisis_notice`）が引き続き走る経路を維持（bulk 経由では当日更新しない）。
- 当日に記録が無ければ従来どおり空欄の新規登録として動作（非回帰）。
- 導線：ホームの本日カードに「本日の記録を修正する」ボタン（当日実測ありのとき）、
  履歴一覧の当日行に「修正する」リンク（当日限定）を追加。

## 6章の設計判断（自由度）

| 論点 | 判断 | 理由 |
| --- | --- | --- |
| 一括登録画面の配置 | 新規ルート `/records/import` | オンボーディングと同じ「じっくり入力」体験を独立画面で再現。モーダルより広い入力域を確保でき、ホーム/履歴からの導線も素直。 |
| Step2 との共通化 | ①パース/検証を `lib/records-import.ts` に抽出 ②入力 UI を `components/BulkRecordEntry.tsx` に抽出し**両画面が同一コンポーネントを描画** | パース関数だけでなく入力 UI ごと共有し、重複コピーを一切残さない（保守性・タイブレーク観点）。送信/画面遷移だけを各画面の責務に残す疎結合設計。 |
| 機能B の更新経路 | `POST /api/records`（同日 UPSERT） | 既存の体調入力フローを踏襲。突合・危機検知が同一 tx で走る既存挙動をそのまま活かせ、`PUT` への切替による差分・回帰リスクを避けられる。 |
| プリフィルのデータ源 | `GET /api/records?from=today&to=today` を再利用 | 単日取得 API を足さずに既存だけで完結。RLS・API 面を増やさない。 |
| 逆ガードの実装場所 | `/onboarding` ページ側で `getProfile` 判定 | `(onboarding)` グループは `OnboardingGate`（`(app)` 側）の対象外。ここに完了判定を置くのが素直で、degrade 方針とも一致。判定中はスピナーを出し、完了済みユーザーへのウィザード点滅を防止。 |
| API 追加 | 追加なし | 仕様の「既存 API 再利用第一」に沿い、bulk / POST records / listRecords の既存3経路で全 AC を満たせたため。 |

## 変更・追加ファイル
- 追加: `frontend/lib/records-import.ts`（共通パース/検証ロジック）
- 追加: `frontend/components/BulkRecordEntry.tsx`（共通入力コンポーネント）
- 追加: `frontend/app/(app)/records/import/page.tsx`（後追い一括登録画面）
- 変更: `frontend/app/(onboarding)/onboarding/page.tsx`（共通化への差し替え＋逆ガード）
- 変更: `frontend/app/(app)/record/page.tsx`（当日プリフィル＋差し替え表示）
- 変更: `frontend/app/(app)/page.tsx`（導線：修正ボタン・過去記録追加メニュー）
- 変更: `frontend/app/(app)/history/page.tsx`（導線：当日行の修正リンク）
- 変更: `frontend/app/globals.css`（`a.btn` 下線除去・`.history-edit` 追加）

バックエンドは無改変（既存 API のみ再利用）。よってバックエンドユニットテストの追加・更新は不要。

## 第4章 AC 自己チェック

### 4.1 機能A：後追い一括登録
- [x] オンボ完了後もいつでも一括登録できる画面がある → `/records/import`
- [x] CSV貼り付け・手入力の両対応 → `BulkRecordEntry`（Step2 と同一）
- [x] アプリ内導線 → ホームメニュー「過去の記録を追加」
- [x] 既存日付は UPSERT 上書きの明示 → 画面上部の注意書き（登録前に常時表示）
- [x] `POST /api/records/bulk`（`bulkRecords`）再利用・新 API なし
- [x] 検証（実在日・未来日不可・1〜10整数・730件上限・同一日付後勝ち）は Step2 と同一（`lib/records-import.ts` を両者が参照）
- [x] Step2 と共通化・重複コピーなし → ロジック＋入力 UI を共有
- [x] 保存失敗時はやさしいエラー＋再試行 → `error-note`、ボタンで再試行

### 4.2 機能A：逆ガード
- [x] 完了済みが `/onboarding` に来たらホームへ送る
- [x] 既存 `OnboardingGate` の一方向ガードを壊さず逆方向を追加・degrade と非矛盾
- [x] 判定基準は `profiles.onboarded_at`（`getProfile()`）

### 4.3 機能B：当日プリフィル・差し替え
- [x] 当日記録があればスコア・コメントをプリフィル
- [x] 「記録済み→差し替え」と分かる（見出し・注意書き・ボタン・トースト）
- [x] 編集して保存で当日記録が更新（差し替え）される
- [x] ホーム・履歴から当日再編集に入れる導線（当日限定）
- [x] 差し替え保存でも突合・危機検知が再実行される経路（`POST /api/records`）を維持
- [x] 取得は `GET /api/records?from=today&to=today` 再利用、RLS 不変
- [x] 当日記録が無ければ従来どおり空欄の新規登録（非回帰）

### 4.4 共通
- [x] `npm run lint` パス（0 errors。既存 `lib/supabase.ts` の warning 1 件は本実装対象外で無改変）
- [x] `npm run build` パス（下記コマンドで env を与えたとき 12/12 ルート prerender 成功）
- [x] バックエンド無改変 → ユニットテスト追加不要
- [x] コード内コメントは日本語（既存トーン準拠）
- [x] 既存トーン・CSS クラスを流用（低彩度パステル・角丸・やさしい語りかけ）
- [x] `.env`・秘匿値のコミット/ハードコードなし（ビルド用の公開ダミー値はコマンド引数で一時付与、未コミット）

## lint / build 実行コマンドと結果

```bash
cd frontend
npm install          # 依存導入（完了）
npm run lint         # → ✖ 1 problem (0 errors, 1 warning)  ※warning は既存 lib/supabase.ts、無改変
```

build は Supabase の公開 env（`NEXT_PUBLIC_*`）が未設定だと prerender が
`supabaseUrl is required` で失敗します。これは**ベースブランチ由来の既存事象**
（`/factors` など既存ページでも同様に失敗）で、本実装が持ち込んだものではありません。
CI/ビルド環境と同じく公開 env を与えると成功します：

```bash
cd frontend
NEXT_PUBLIC_SUPABASE_URL="https://<your-project>.supabase.co" \
NEXT_PUBLIC_SUPABASE_ANON_KEY="<anon-key>" \
NEXT_PUBLIC_API_BASE="http://localhost:8000" \
  npm run build
# → ✓ Compiled successfully / ✓ Generating static pages (12/12)
#   /records/import を含む全ルートが static prerender 成功
```

## 既知の制約・前提・TODO
- build には公開 Supabase env（anon 鍵）が必要（既存前提。ローカルは `frontend/.env`、CI は env で供給）。
- 機能B のプリフィルは `listRecords(today, today)` の1回取得。取得失敗時は新規登録として degrade する（プリフィルは補助的位置づけ）。
- 対象外スコープ（過去日1件の個別編集・エクスポート・物理削除）は未実装（仕様どおり）。
- ブラウザ実機での目視確認は Supabase 認証＋FastAPI＋DB の全スタック起動が必要なため未実施。
  型検査を含む `npm run build` の全ルート prerender 成功をもって画面の描画健全性を確認済み。
