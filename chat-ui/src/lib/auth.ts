/**
 * Engram — Frontend Auth Helpers
 * Stores JWT in localStorage, provides typed helpers for sign in/up/out.
 */

const TOKEN_KEY = "engram_token";
const USER_KEY  = "engram_user";

export interface User {
  user_id: string;
  email: string;
  username: string;
}

// ── Token storage ─────────────────────────────────────────────────

export function saveSession(token: string, user: User) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getUser(): User | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

export function isLoggedIn(): boolean {
  return !!getToken();
}

// ── API calls ──────────────────────────────────────────────────────

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface AuthResponse {
  token: string;
  user_id: string;
  email: string;
  username: string;
}

async function authPost(path: string, body: object): Promise<AuthResponse> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || data.error || `HTTP ${res.status}`);
  }
  return data;
}

export async function register(email: string, username: string, password: string): Promise<User> {
  const resp = await authPost("/auth/register", { email, username, password });
  const user: User = { user_id: resp.user_id, email: resp.email, username: resp.username };
  saveSession(resp.token, user);
  return user;
}

export async function login(email: string, password: string): Promise<User> {
  const resp = await authPost("/auth/login", { email, password });
  const user: User = { user_id: resp.user_id, email: resp.email, username: resp.username };
  saveSession(resp.token, user);
  return user;
}

export function logout() {
  clearSession();
  window.location.href = "/auth";
}
