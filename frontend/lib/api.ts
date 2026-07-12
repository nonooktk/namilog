// FastAPI クライアントの骨組み（ARCHITECTURE.md §8.1）。
//
// すべてのデータアクセスはこのクライアント経由で FastAPI を叩く（P-1）。
// Supabase の access_token(JWT) を Authorization: Bearer に付与する（§1.3）。
// M2 では骨組みまで。各画面のデータ取得フックはイーブイが後続で実装する。

import { getAccessToken } from "./supabase";
import type {
  FeedbackListResponse,
  FeedbackPostResponse,
  FactorSuggestResponse,
  NotesCurrentResponse,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(`API エラー (${status})`);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const token = await getAccessToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    // 認証は JWT ヘッダで行うため cookie は送らない。
    credentials: "omit",
  });

  if (!res.ok) {
    let detail: unknown = null;
    try {
      detail = await res.json();
    } catch {
      detail = await res.text();
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
};

// ---- M2 対象エンドポイントの薄いラッパ（型は M3/画面実装時に精緻化）----
export const namilogApi = {
  getProfile: () => api.get("/api/profile"),
  updateProfile: (body: unknown) => api.put("/api/profile", body),
  bulkRecords: (records: unknown[]) => api.post("/api/records/bulk", { records }),
  createRecord: (body: unknown) => api.post("/api/records", body),
  updateRecord: (date: string, body: unknown) => api.put(`/api/records/${date}`, body),
  listRecords: (from?: string, to?: string) =>
    api.get(`/api/records${qs({ from, to })}`),
  getSeries: (from?: string, to?: string) =>
    api.get(`/api/history/series${qs({ from, to })}`),
  getCatalog: () => api.get("/api/factors/catalog"),
  getSelection: () => api.get("/api/factors/selection"),
  putSelection: (factor_keys: string[]) =>
    api.put("/api/factors/selection", { factor_keys }),
  putFactorValues: (date: string, values: Record<string, unknown>) =>
    api.put(`/api/factor-values/${date}`, { values }),
  getHome: () => api.get("/api/home"),

  // ---- M3: FB チャット / AI 提案 / 予測ノート（型付きで返す） ----
  /** 会話履歴を取得（NL-API-14）。prediction_id 指定でその予測の会話に絞る。昇順。 */
  getFeedback: (prediction_id?: string | null, limit = 50) =>
    api.get<FeedbackListResponse>(
      `/api/feedback${qs({ prediction_id: prediction_id ?? undefined, limit: String(limit) })}`,
    ),
  /** 発話を送信（NL-API-15）。user 保存 → GPT 応答 → assistant 保存。空文字は 422。 */
  postFeedback: (content: string, prediction_id: string | null = null) =>
    api.post<FeedbackPostResponse>("/api/feedback", { prediction_id, content }),
  /** AI 入れ替え提案（NL-API-13）。採否は本人が selection 更新で行う。 */
  suggestFactor: () =>
    api.post<FactorSuggestResponse>("/api/factors/suggest"),
  /** 現行の予測ノートを取得（NL-API-18）。未作成なら note=null。 */
  getCurrentNote: () => api.get<NotesCurrentResponse>("/api/notes/current"),
};

function qs(params: Record<string, string | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v != null && v !== "");
  if (entries.length === 0) return "";
  return "?" + entries.map(([k, v]) => `${k}=${encodeURIComponent(v as string)}`).join("&");
}
