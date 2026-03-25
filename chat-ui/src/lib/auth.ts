/**
 * Engram — Frontend Auth Helpers
 * Stores JWT in localStorage, provides typed helpers for sign in/up/out.
 */

const ACCESS_TOKEN_KEY  = "engram_token";
const REFRESH_TOKEN_KEY = "engram_refresh_token";
const USER_KEY          = "engram_user";

export interface User {
  user_id:  string;
  email:    string;
  username: string;
}

// ── Session storage ───────────────────────────────────────────────

export function saveSession(accessToken: string, refreshToken: string, user: User) {
  localStorage.setItem(ACCESS_TOKEN_KEY,  accessToken);
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  localStorage.setItem(USER_KEY,          JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_TOKEN_KEY);
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

function _decodeJwt(token: string): Record<string, unknown> | null {
  try {
    const [, body] = token.split(".");
    const pad = 4 - (body.length % 4);
    const padded = body + "=".repeat(pad === 4 ? 0 : pad);
    return JSON.parse(atob(padded.replace(/-/g, "+").replace(/_/g, "/")));
  } catch {
    return null;
  }
}

export function accessTokenNeedsRefresh(): boolean {
  const token = getToken();
  if (!token) return true;
  const payload = _decodeJwt(token);
  if (!payload || typeof payload.exp !== "number") return true;
  return payload.exp - Math.floor(Date.now() / 1000) < 60;
}

// ── API calls ─────────────────────────────────────────────────────

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface AuthResponse {
  access_token:  string;
  refresh_token: string;
  user_id:       string;
  email:         string;
  username:      string;
}

async function authPost(path: string, body: object): Promise<AuthResponse> {
  const res = await fetch(`${API}${path}`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || data.error || `HTTP ${res.status}`);
  return data;
}

export async function register(email: string, username: string, password: string): Promise<User> {
  const resp = await authPost("/auth/register", { email, username, password });
  const user: User = { user_id: resp.user_id, email: resp.email, username: resp.username };
  saveSession(resp.access_token, resp.refresh_token, user);
  return user;
}

export async function login(email: string, password: string): Promise<User> {
  const resp = await authPost("/auth/login", { email, password });
  const user: User = { user_id: resp.user_id, email: resp.email, username: resp.username };
  saveSession(resp.access_token, resp.refresh_token, user);
  return user;
}


export async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) { logout(); return null; }

  try {
    const res = await fetch(`${API}/auth/refresh`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) { logout(); return null; }
    const data = await res.json();
    localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token);
    return data.access_token;
  } catch {
    logout();
    return null;
  }
}

export async function logout() {
  const refreshToken = getRefreshToken();
  if (refreshToken) {
    fetch(`${API}/auth/logout`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ refresh_token: refreshToken }),
    }).catch(() => {});
  }
  clearSession();
  window.location.href = "/auth";
}
