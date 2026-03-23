const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Memory {
  id: string;
  content: string;
  score?: number;
  rerank_score?: number;
  tags: string[];
  created_at?: string;
  graph_rel?: string;
}

export interface StoreResult {
  stored: number;
  skipped_duplicates: number;
  contradictions_resolved: number;
  graph_edges: number;
  facts: string[];
}

export interface RecallResult {
  query: string;
  memories: Memory[];
  total_found: number;
  context_tokens: number;
}

export interface ChatResult {
  response: string;
  memories_used: number;
}

export interface HealthResult {
  status: string;
  timestamp: string;
  model: string;
  graph: { nodes: number; edges: number; updates: number; extends: number; derives: number };
}

export interface ApiError {
  error: string;  
  code: string;    
  status: number;
}

export class EngramApiError extends Error {
  code: string;
  status: number;
  constructor(err: ApiError) {
    super(err.error);
    this.code = err.code;
    this.status = err.status;
  }
}

async function post<T>(path: string, body: object): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => null);
    if (payload && payload.error && payload.code) {
      throw new EngramApiError(payload as ApiError);
    }
    throw new EngramApiError({
      error: payload?.detail ?? `Request failed (${res.status})`,
      code: "UNKNOWN",
      status: res.status,
    });
  }
  return res.json();
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) {
    const payload = await res.json().catch(() => null);
    if (payload && payload.error) throw new EngramApiError(payload as ApiError);
    throw new EngramApiError({ error: `HTTP ${res.status}`, code: "HTTP_ERROR", status: res.status });
  }
  return res.json();
}

export function friendlyError(e: unknown): string {
  if (e instanceof EngramApiError) return e.message;
  if (e instanceof Error) return e.message;
  return "Something went wrong. Please try again.";
}

export const api = {
  health: () => get<HealthResult>("/health"),

  store: (content: string, userId = "default", tags: string[] = []) =>
    post<StoreResult>("/memory/store", { content, user_id: userId, tags }),

  recall: (query: string, userId = "default") =>
    post<RecallResult>("/memory/recall", { query, user_id: userId }),

  chat: (message: string, userId = "default", history: { role: string; content: string }[] = []) =>
    post<ChatResult>("/chat", { message, user_id: userId, history }),

  list: (userId = "default", limit = 50) =>
    get<Memory[]>(`/memory/list/${userId}?limit=${limit}`),

  delete: (memoryId: string) =>
    fetch(`${API}/memory/${memoryId}`, { method: "DELETE" }).then((r) => r.json()),
};
