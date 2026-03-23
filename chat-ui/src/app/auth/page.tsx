"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { login, register, isLoggedIn } from "@/lib/auth";

type Mode = "signin" | "signup";

export default function AuthPage() {
  const router = useRouter();
  const [mode, setMode]       = useState<Mode>("signin");
  const [email, setEmail]     = useState("");
  const [username, setUser]   = useState("");
  const [password, setPass]   = useState("");
  const [error, setError]     = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isLoggedIn()) router.replace("/");
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (mode === "signin") {
        await login(email, password);
      } else {
        if (username.length < 3) { setError("Username must be at least 3 characters"); setLoading(false); return; }
        if (password.length < 8) { setError("Password must be at least 8 characters"); setLoading(false); return; }
        await register(email, username, password);
      }
      router.replace("/");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-ink-950 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">

        {/* Logo */}
        <div className="text-center mb-8">
          <h1 className="font-display text-3xl text-ink-50 tracking-tight">Engram</h1>
          <p className="text-ink-500 text-sm mt-1 font-mono">memory layer</p>
        </div>

        {/* Card */}
        <div className="bg-ink-800 border border-ink-700 rounded-2xl p-6">

          {/* Tabs */}
          <div className="flex gap-1 bg-ink-900 rounded-xl p-1 mb-6">
            {(["signin", "signup"] as Mode[]).map((m) => (
              <button
                key={m}
                onClick={() => { setMode(m); setError(""); }}
                className={`flex-1 py-2 text-sm font-medium rounded-lg transition-all duration-150 ${
                  mode === m
                    ? "bg-volt-500 text-white"
                    : "text-ink-400 hover:text-ink-200"
                }`}
              >
                {m === "signin" ? "Sign in" : "Sign up"}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="space-y-4">
            {/* Email */}
            <div>
              <label className="block text-xs text-ink-400 uppercase tracking-wider mb-1.5 font-mono">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="you@example.com"
                className="w-full bg-ink-900 border border-ink-600 rounded-xl px-4 py-2.5 text-sm text-ink-100 placeholder-ink-600 outline-none focus:border-volt-500/60 transition-colors"
              />
            </div>

            {/* Username — sign up only */}
            {mode === "signup" && (
              <div>
                <label className="block text-xs text-ink-400 uppercase tracking-wider mb-1.5 font-mono">
                  Username
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUser(e.target.value)}
                  required
                  placeholder="yourname"
                  minLength={3}
                  maxLength={50}
                  className="w-full bg-ink-900 border border-ink-600 rounded-xl px-4 py-2.5 text-sm text-ink-100 placeholder-ink-600 outline-none focus:border-volt-500/60 transition-colors"
                />
              </div>
            )}

            {/* Password */}
            <div>
              <label className="block text-xs text-ink-400 uppercase tracking-wider mb-1.5 font-mono">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPass(e.target.value)}
                required
                placeholder={mode === "signup" ? "Min 8 characters" : "••••••••"}
                minLength={mode === "signup" ? 8 : 1}
                className="w-full bg-ink-900 border border-ink-600 rounded-xl px-4 py-2.5 text-sm text-ink-100 placeholder-ink-600 outline-none focus:border-volt-500/60 transition-colors"
              />
            </div>

            {/* Error */}
            {error && (
              <div className="flex items-center gap-2 bg-ember-500/10 border border-ember-500/20 rounded-xl px-4 py-3">
                <span className="text-ember-400 text-sm">⚠</span>
                <p className="text-ember-300 text-sm">{error}</p>
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 bg-volt-500 hover:bg-volt-400 disabled:opacity-40 text-white text-sm font-medium rounded-xl transition-all duration-150 mt-2"
            >
              {loading
                ? (mode === "signin" ? "Signing in…" : "Creating account…")
                : (mode === "signin" ? "Sign in" : "Create account")}
            </button>
          </form>

          {/* Switch mode */}
          <p className="text-center text-ink-500 text-xs mt-5">
            {mode === "signin" ? "No account? " : "Already have an account? "}
            <button
              onClick={() => { setMode(mode === "signin" ? "signup" : "signin"); setError(""); }}
              className="text-volt-400 hover:text-volt-300 transition-colors"
            >
              {mode === "signin" ? "Sign up" : "Sign in"}
            </button>
          </p>
        </div>

        <p className="text-center text-ink-600 text-xs mt-6">
          Your data stays on your machine. No cloud storage.
        </p>
      </div>
    </div>
  );
}
