"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { api, Memory, friendlyError, EngramApiError } from "@/lib/api";
import { getUser, logout, isLoggedIn, type User } from "@/lib/auth";

// ── Types ─────────────────────────────────────────────────────────

type Role = "user" | "assistant";
interface Message {
  id: string;
  role: Role;
  content: string;
  memoriesUsed?: number;
  isThinking?: boolean;
  isError?: boolean;
}
type Tab = "chat" | "memories" | "onboarding";

// ── Onboarding questions (cold-start seeder) ──────────────────────

const ONBOARDING_QUESTIONS = [
  "What is your full name and what do you do professionally?",
  "What are your main technical skills or areas of expertise?",
  "What projects are you currently working on?",
  "What are your long-term goals — personal and professional?",
  "What do you like and dislike? (hobbies, foods, preferences)",
  "Who are the important people in your life? (colleagues, family, friends)",
  "What tools, languages, or frameworks do you use daily?",
  "What topics are you actively learning or researching right now?",
  "Do you have any recurring commitments, routines, or constraints I should know about?",
  "Is there anything else important about you that you'd want me to always remember?",
];

// ── Utility ───────────────────────────────────────────────────────

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

// Minimal markdown → html (bold, code, newlines)
function renderMarkdown(text: string) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br>");
}

// ── Sub-components ────────────────────────────────────────────────

function Dot({ online }: { online: boolean | null }) {
  if (online === null)
    return <span className="w-2 h-2 rounded-full bg-ink-500 animate-pulse-dot inline-block" />;
  return (
    <span
      className={`w-2 h-2 rounded-full inline-block transition-colors duration-500 ${
        online ? "bg-jade-500" : "bg-ember-500"
      }`}
    />
  );
}

function ThinkingBubble() {
  return (
    <div className="flex gap-1 items-center px-4 py-3">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-volt-400 animate-thinking"
          style={{ animationDelay: `${i * 0.2}s` }}
        />
      ))}
    </div>
  );
}

function MemoryBadge({ count }: { count: number }) {
  if (!count) return null;
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-mono text-volt-400 bg-volt-500/10 border border-volt-500/20 rounded-full px-2 py-0.5 ml-2">
      ⬡ {count} mem
    </span>
  );
}

// ── Main component ────────────────────────────────────────────────

export default function Home() {
  const [user, setUser] = useState<User | null>(null);
  const userId = user?.user_id ?? "default";
  const [tab, setTab] = useState<Tab>("chat");
  const [online, setOnline] = useState<boolean | null>(null);
  const [graphStats, setGraphStats] = useState({ nodes: 0, edges: 0 });

  // Chat
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Memories
  const [memories, setMemories] = useState<Memory[]>([]);
  const [memSearch, setMemSearch] = useState("");
  const [loadingMem, setLoadingMem] = useState(false);

  // Onboarding
  const [obStep, setObStep] = useState(0);
  const [obAnswers, setObAnswers] = useState<string[]>(Array(ONBOARDING_QUESTIONS.length).fill(""));
  const [obSaving, setObSaving] = useState(false);
  const [obDone, setObDone] = useState(false);

  // ── Init ───────────────────────────────────────────────────────

  useEffect(() => {
    // Redirect to auth if not logged in
    const currentUser = getUser();
    if (!currentUser || !isLoggedIn()) {
      window.location.href = "/auth";
      return;
    }
    setUser(currentUser);

    api.health()
      .then((h) => {
        setOnline(true);
        setGraphStats(h.graph);
      })
      .catch(() => setOnline(false));
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Chat ───────────────────────────────────────────────────────

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;

    const userMsg: Message = { id: uid(), role: "user", content: text };
    const thinkingMsg: Message = { id: uid(), role: "assistant", content: "", isThinking: true };

    setMessages((prev) => [...prev, userMsg, thinkingMsg]);
    setInput("");
    setSending(true);

    const history = messages
      .filter((m) => !m.isThinking)
      .map((m) => ({ role: m.role, content: m.content }));

    try {
      const result = await api.chat(text, userId, history);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === thinkingMsg.id
            ? { ...m, content: result.response, isThinking: false, memoriesUsed: result.memories_used }
            : m
        )
      );
    } catch (e: unknown) {
      const msg = friendlyError(e);
      const isQuota = e instanceof EngramApiError && (e.code === "QUOTA_RPM" || e.code === "QUOTA_DAILY");
      setMessages((prev) =>
        prev.map((m) =>
          m.id === thinkingMsg.id
            ? { ...m, content: msg, isThinking: false, isError: true }
            : m
        )
      );
      if (isQuota) setSending(false);
    } finally {
      setSending(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [input, sending, messages, userId]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // ── Memories tab ───────────────────────────────────────────────

  const loadMemories = useCallback(async () => {
    setLoadingMem(true);
    try {
      const list = await api.list(userId, 100);
      setMemories(list);
    } catch {
      setMemories([]);
    } finally {
      setLoadingMem(false);
    }
  }, [userId]);

  useEffect(() => {
    if (tab === "memories") loadMemories();
  }, [tab, loadMemories]);

  const deleteMemory = async (id: string) => {
    await api.delete(id);
    setMemories((prev) => prev.filter((m) => m.id !== id));
  };

  const filteredMemories = memories.filter((m) =>
    m.content.toLowerCase().includes(memSearch.toLowerCase())
  );

  // ── Onboarding ─────────────────────────────────────────────────

  const saveOnboardingAnswer = async () => {
    const answer = obAnswers[obStep].trim();
    if (!answer) return;
    setObSaving(true);
    try {
      await api.store(
        `${ONBOARDING_QUESTIONS[obStep]}\n${answer}`,
        userId,
        ["onboarding"]
      );
    } catch {/* non-fatal */}
    setObSaving(false);

    if (obStep < ONBOARDING_QUESTIONS.length - 1) {
      setObStep((s) => s + 1);
    } else {
      setObDone(true);
    }
  };

  // ── Render ─────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-screen bg-ink-950 font-body">

      {/* ── Header ────────────────────────────────────────────── */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-ink-700 bg-ink-900/80 backdrop-blur-sm shrink-0">
        <div className="flex items-center gap-3">
          <span className="font-display text-xl text-ink-50 tracking-tight">Engram</span>
          <span className="text-ink-500 text-xs font-mono">memory layer</span>
        </div>
        <div className="flex items-center gap-4">
          {/* Graph stats */}
          <span className="text-ink-500 text-xs font-mono hidden sm:block">
            ⬡ {graphStats.nodes} nodes · {graphStats.edges} edges
          </span>
          {/* Status */}
          <div className="flex items-center gap-1.5 text-xs text-ink-400">
            <Dot online={online} />
            <span>{online === null ? "connecting" : online ? "online" : "offline"}</span>
          </div>
          {/* User + logout */}
          {user && (
            <div className="flex items-center gap-2 border-l border-ink-700 pl-4">
              <span className="text-xs text-ink-400 hidden sm:block">{user.username}</span>
              <button
                onClick={logout}
                className="text-xs text-ink-500 hover:text-ember-400 transition-colors px-2 py-1 rounded-lg hover:bg-ink-800"
                title="Sign out"
              >
                Sign out
              </button>
            </div>
          )}
        </div>
      </header>

      {/* ── Tabs ──────────────────────────────────────────────── */}
      <div className="flex gap-0 border-b border-ink-700 shrink-0 bg-ink-900/50">
        {(["chat", "memories", "onboarding"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-5 py-2.5 text-sm font-medium transition-all duration-150 border-b-2 ${
              tab === t
                ? "border-volt-400 text-volt-300"
                : "border-transparent text-ink-400 hover:text-ink-200"
            }`}
          >
            {t === "chat" && "💬 Chat"}
            {t === "memories" && `🧠 Memories${memories.length ? ` (${memories.length})` : ""}`}
            {t === "onboarding" && "✦ Onboarding"}
          </button>
        ))}
      </div>

      {/* ── Chat tab ──────────────────────────────────────────── */}
      {tab === "chat" && (
        <div className="flex flex-col flex-1 min-h-0">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full text-center gap-3 animate-fade-up">
                <span className="text-5xl">🧠</span>
                <p className="font-display text-2xl text-ink-200">What's on your mind?</p>
                <p className="text-ink-500 text-sm max-w-sm">
                  Your memories are automatically recalled and injected as context with every message.
                </p>
              </div>
            )}

            {messages.map((msg, i) => (
              <div
                key={msg.id}
                className={`flex animate-fade-up ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                style={{ animationDelay: `${Math.min(i * 0.03, 0.3)}s` }}
              >
                {msg.role === "user" ? (
                  <div className="max-w-[75%] bg-volt-500/20 border border-volt-500/30 rounded-2xl rounded-tr-sm px-4 py-3 text-ink-100 text-sm leading-relaxed">
                    {msg.content}
                  </div>
                ) : (
                  <div className="max-w-[80%]">
                    <div className="bg-ink-800 border border-ink-700 rounded-2xl rounded-tl-sm px-4 py-3 text-ink-100 text-sm">
                      {msg.isThinking ? (
                        <ThinkingBubble />
                      ) : msg.isError ? (
                        <div className="flex items-start gap-2.5">
                          <span className="text-ember-400 mt-0.5 shrink-0">⚠</span>
                          <p className="text-ember-300 text-sm leading-relaxed">{msg.content}</p>
                        </div>
                      ) : (
                        <div
                          className="prose-engram"
                          dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
                        />
                      )}
                    </div>
                    {!msg.isThinking && msg.memoriesUsed !== undefined && (
                      <div className="mt-1 pl-1">
                        <MemoryBadge count={msg.memoriesUsed} />
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="shrink-0 px-4 pb-4 pt-2 border-t border-ink-700 bg-ink-900/50">
            <div className="flex gap-2 items-end bg-ink-800 border border-ink-600 rounded-2xl p-2 focus-within:border-volt-500/50 transition-colors">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Message Engram… (Enter to send, Shift+Enter for newline)"
                rows={1}
                className="flex-1 bg-transparent text-ink-100 text-sm placeholder-ink-500 resize-none outline-none px-2 py-1.5 max-h-40 overflow-y-auto font-body leading-relaxed"
                style={{ fieldSizing: "content" } as React.CSSProperties}
              />
              <button
                onClick={sendMessage}
                disabled={!input.trim() || sending}
                className="shrink-0 w-9 h-9 rounded-xl bg-volt-500 hover:bg-volt-400 disabled:opacity-30 disabled:cursor-not-allowed transition-all duration-150 flex items-center justify-center"
              >
                <svg className="w-4 h-4 text-white" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M1 8l7-7 7 7M8 1v14" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round"/>
                </svg>
              </button>
            </div>
            <p className="text-center text-ink-600 text-xs mt-2">
              Memories recalled from your personal knowledge base
            </p>
          </div>
        </div>
      )}

      {/* ── Memories tab ──────────────────────────────────────── */}
      {tab === "memories" && (
        <div className="flex flex-col flex-1 min-h-0 p-4 gap-3">
          {/* Search + refresh */}
          <div className="flex gap-2 shrink-0">
            <input
              value={memSearch}
              onChange={(e) => setMemSearch(e.target.value)}
              placeholder="Search memories…"
              className="flex-1 bg-ink-800 border border-ink-700 rounded-xl px-4 py-2.5 text-sm text-ink-100 placeholder-ink-500 outline-none focus:border-volt-500/50 transition-colors"
            />
            <button
              onClick={loadMemories}
              className="px-4 py-2.5 bg-ink-800 border border-ink-700 rounded-xl text-ink-400 hover:text-ink-200 hover:border-ink-500 text-sm transition-all"
            >
              ↻
            </button>
          </div>

          {/* Memory list */}
          <div className="flex-1 overflow-y-auto space-y-2">
            {loadingMem && (
              <div className="text-center text-ink-500 py-8 text-sm">Loading…</div>
            )}
            {!loadingMem && filteredMemories.length === 0 && (
              <div className="text-center text-ink-500 py-12 text-sm">
                {memSearch ? "No memories match that search." : "No memories yet. Start chatting!"}
              </div>
            )}
            {filteredMemories.map((m, i) => (
              <div
                key={m.id}
                className="group bg-ink-800 border border-ink-700 rounded-xl px-4 py-3 hover:border-ink-500 transition-all duration-150 animate-fade-up"
                style={{ animationDelay: `${i * 0.02}s` }}
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm text-ink-100 leading-relaxed flex-1">{m.content}</p>
                  <button
                    onClick={() => deleteMemory(m.id)}
                    className="shrink-0 opacity-0 group-hover:opacity-100 text-ink-500 hover:text-ember-400 text-xs transition-all"
                    title="Delete memory"
                  >
                    ✕
                  </button>
                </div>
                <div className="flex items-center gap-3 mt-2">
                  {m.tags?.map((tag) => (
                    <span key={tag} className="text-[10px] font-mono text-ink-500 bg-ink-700 px-2 py-0.5 rounded-full">
                      {tag}
                    </span>
                  ))}
                  {m.created_at && (
                    <span className="text-[10px] text-ink-600 ml-auto font-mono">
                      {timeAgo(m.created_at)}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Footer count */}
          <div className="shrink-0 text-center text-ink-600 text-xs font-mono">
            {filteredMemories.length} of {memories.length} memories
          </div>
        </div>
      )}

      {/* ── Onboarding tab ────────────────────────────────────── */}
      {tab === "onboarding" && (
        <div className="flex flex-col flex-1 min-h-0 items-center justify-center p-6">
          {obDone ? (
            <div className="text-center animate-fade-up space-y-4">
              <div className="text-5xl">✦</div>
              <p className="font-display text-2xl text-ink-100">Memory seeded.</p>
              <p className="text-ink-400 text-sm max-w-sm">
                Engram now knows you. Start chatting — your memories will be recalled automatically.
              </p>
              <button
                onClick={() => setTab("chat")}
                className="mt-4 px-6 py-2.5 bg-volt-500 hover:bg-volt-400 text-white text-sm font-medium rounded-xl transition-all"
              >
                Start chatting →
              </button>
            </div>
          ) : (
            <div className="w-full max-w-lg space-y-6 animate-fade-up">
              {/* Progress */}
              <div className="space-y-2">
                <div className="flex justify-between text-xs text-ink-500 font-mono">
                  <span>Cold start · question {obStep + 1} of {ONBOARDING_QUESTIONS.length}</span>
                  <span>{Math.round(((obStep) / ONBOARDING_QUESTIONS.length) * 100)}%</span>
                </div>
                <div className="h-1 bg-ink-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-volt-500 rounded-full transition-all duration-500"
                    style={{ width: `${(obStep / ONBOARDING_QUESTIONS.length) * 100}%` }}
                  />
                </div>
              </div>

              {/* Question */}
              <div className="bg-ink-800 border border-ink-700 rounded-2xl p-6 space-y-4">
                <p className="font-display text-lg text-ink-100 leading-snug">
                  {ONBOARDING_QUESTIONS[obStep]}
                </p>
                <textarea
                  value={obAnswers[obStep]}
                  onChange={(e) => {
                    const next = [...obAnswers];
                    next[obStep] = e.target.value;
                    setObAnswers(next);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) saveOnboardingAnswer();
                  }}
                  placeholder="Your answer…"
                  rows={4}
                  className="w-full bg-ink-900 border border-ink-600 rounded-xl px-4 py-3 text-sm text-ink-100 placeholder-ink-500 outline-none focus:border-volt-500/50 resize-none transition-colors font-body leading-relaxed"
                />
                <div className="flex gap-3 justify-between items-center">
                  <button
                    onClick={() => setObStep((s) => Math.max(0, s - 1))}
                    disabled={obStep === 0}
                    className="text-sm text-ink-500 hover:text-ink-300 disabled:opacity-30 transition-colors"
                  >
                    ← Back
                  </button>
                  <button
                    onClick={saveOnboardingAnswer}
                    disabled={!obAnswers[obStep].trim() || obSaving}
                    className="px-5 py-2 bg-volt-500 hover:bg-volt-400 disabled:opacity-30 text-white text-sm font-medium rounded-xl transition-all"
                  >
                    {obSaving ? "Saving…" : obStep === ONBOARDING_QUESTIONS.length - 1 ? "Finish ✓" : "Save & next →"}
                  </button>
                </div>
              </div>

              <p className="text-center text-ink-600 text-xs">
                Answers are stored privately in your local Engram instance. Ctrl+Enter to save.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
