// FastAPI（backend/app/routers/*）のレスポンス形状に対応する型。
// lib/api.ts（ポリゴン作）の namilogApi.* は戻り値 unknown のため、
// 各画面でこの型にキャストして扱う（api.ts 自体は変更しない＝非侵襲）。

/** スコア帯（1-3 low / 4-6 mid / 7-10 high）。信号色を使わず色だけに依存しない（デザイン2.4）。 */
export type ScoreBand = "low" | "mid" | "high";

// ---- ホーム（NL-API-05: GET /api/home） ----
export interface HomePrediction {
  target_date?: string;
  predicted_score: number;
  advice: string;
  rationale: string;
  crisis_flag: boolean;
}
export interface HomeActual {
  actual_score: number;
  comment: string | null;
}
export interface HomeResponse {
  today: {
    actual: HomeActual | null;
    prediction: HomePrediction | null;
  };
  tomorrow: {
    prediction: HomePrediction | null;
  };
  notice: string | null;
  crisis_notice: boolean;
}

// ---- 体調記録（NL-API-06/07: POST/PUT /api/records） ----
export interface DailyRecord {
  id: string;
  record_date: string;
  actual_score: number;
  comment: string | null;
  updated_at: string;
}
export interface MatchedPrediction {
  predicted_score: number;
  actual_score: number;
  error: number;
  abs_error: number;
}
export interface RecordMutationResponse {
  record: DailyRecord;
  matched_prediction: MatchedPrediction | null;
  crisis_notice: boolean;
}

// ---- 履歴一覧（NL-API-09: GET /api/records） ----
export interface HistoryRow {
  date: string;
  actual_score: number | null;
  comment: string | null;
  predicted_score: number | null;
  advice: string | null;
  error: number | null;
  abs_error: number | null;
}
export interface ListRecordsResponse {
  records: HistoryRow[];
}

// ---- 波グラフ時系列（NL-API-10: GET /api/history/series） ----
export interface SeriesPoint {
  date: string;
  actual: number | null;
  predicted: number | null;
}
export interface SeriesResponse {
  series: SeriesPoint[];
}

// ---- 指標カタログ（NL-API-03: GET /api/factors/catalog） ----
export type FactorInputType = "open_meteo" | "derived" | "manual";
export interface CatalogItem {
  factor_key: string;
  label: string;
  input_type: FactorInputType;
  unit: string | null;
  description: string | null;
  sort_order: number;
}
export interface CatalogResponse {
  catalog: CatalogItem[];
}

// ---- 指標選択（NL-API-11/12: GET/PUT /api/factors/selection） ----
export interface SelectionActive {
  factor_key: string;
  label: string;
  input_type: FactorInputType;
  unit: string | null;
  activated_at: string;
}
export interface SelectionHistory {
  factor_key: string;
  is_active: boolean;
  activated_at: string;
  deactivated_at: string | null;
}
export interface SelectionResponse {
  active: SelectionActive[];
  history: SelectionHistory[];
}

// ---- プロフィール（NL-API-01: GET /api/profile） ----
export interface Profile {
  id: string;
  display_name: string | null;
  latitude: number | null;
  longitude: number | null;
  timezone: string | null;
  medical_disclaimer_agreed_at: string | null;
  onboarded_at: string | null;
  created_at?: string;
  updated_at?: string;
}
