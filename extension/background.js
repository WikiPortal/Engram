/**
 * Engram — Background Service Worker (Step 16)
 *
 * Responsibilities:
 *   1. Receive messages from content.js
 *   2. POST to Engram API (/memory/store, /memory/recall)
 *   3. Return results back to content.js
 *
 * Why background.js handles API calls (not content.js directly):
 *   - Avoids CORS issues on some pages
 *   - Centralises the API base URL and user_id config
 *   - Content scripts have restricted fetch in some CSP environments
 */

const DEFAULT_API = "http://localhost:8000";
const DEFAULT_USER = "default";

// ── Config helpers ────────────────────────────────────────────────

async function getConfig() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(
      { apiBase: DEFAULT_API, userId: DEFAULT_USER, enabled: true },
      resolve
    );
  });
}

// ── API calls ─────────────────────────────────────────────────────

async function storeMemory(content, apiBase, userId) {
  try {
    const resp = await fetch(`${apiBase}/memory/store`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, user_id: userId }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
  } catch (e) {
    console.error("[Engram] store failed:", e.message);
    return null;
  }
}

async function recallMemories(query, apiBase, userId) {
  try {
    const resp = await fetch(`${apiBase}/memory/recall`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, user_id: userId }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
  } catch (e) {
    console.error("[Engram] recall failed:", e.message);
    return null;
  }
}

// ── Message handler ───────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // Must return true to keep the channel open for async response
  (async () => {
    const { apiBase, userId, enabled } = await getConfig();

    if (!enabled) {
      sendResponse({ ok: false, reason: "Engram is disabled" });
      return;
    }

    if (message.type === "RECALL") {
      // content.js asking: what memories are relevant to this query?
      const result = await recallMemories(message.query, apiBase, userId);
      sendResponse({ ok: !!result, data: result });

    } else if (message.type === "STORE") {
      // content.js sending: store this conversation turn
      const result = await storeMemory(message.content, apiBase, userId);
      sendResponse({ ok: !!result, data: result });

    } else {
      sendResponse({ ok: false, reason: "Unknown message type" });
    }
  })();

  return true; // keep message channel open for async
});
