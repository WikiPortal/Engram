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
  graph: { nodes: number; edges: number; updates: number; extends: number; derives: number };
}

async function post<T>(path: string, body: object): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
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
