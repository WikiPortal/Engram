const DEFAULT_API = "http://localhost:8000";
const DEFAULT_USER = "default";

async function getConfig() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(
      { apiBase: DEFAULT_API, userId: DEFAULT_USER, enabled: true },
      resolve
    );
  });
}

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

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    const { apiBase, userId, enabled } = await getConfig();

    if (!enabled) {
      sendResponse({ ok: false, reason: "Engram is disabled" });
      return;
    }

    if (message.type === "RECALL") {
      const result = await recallMemories(message.query, apiBase, userId);
      sendResponse({ ok: !!result, data: result });

    } else if (message.type === "STORE") {
      const result = await storeMemory(message.content, apiBase, userId);
      sendResponse({ ok: !!result, data: result });

    } else {
      sendResponse({ ok: false, reason: "Unknown message type" });
    }
  })();

  return true; // keep message channel open for async
});
