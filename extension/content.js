/**
 * Engram — Content Script (Step 16)
 *
 * Two jobs:
 *   1. INTERCEPT: Before the user sends a prompt, recall relevant memories
 *      and prepend them to the message as context.
 *   2. STORE: After an AI response is received, store the conversation
 *      turn (user message + AI response) as a memory.
 *
 * Targets: claude.ai and chatgpt.com
 * Both sites use a contenteditable div or textarea for the prompt box.
 * We hook the submit button / Enter key to intercept before send.
 */

(function () {
  "use strict";

  // ── Site detection ──────────────────────────────────────────────

  const SITE = window.location.hostname.includes("claude.ai")
    ? "claude"
    : "chatgpt";

  // ── Selectors per site ──────────────────────────────────────────

  const SELECTORS = {
    claude: {
      // The main prompt input (contenteditable div)
      input: '[data-testid="chat-input"], div[contenteditable="true"]',
      // Send button
      sendBtn: '[data-testid="send-button"], button[aria-label="Send Message"]',
      // AI response containers
      response: '[data-testid="chat-message-content"], .font-claude-message',
      // Human turn containers
      humanTurn: '[data-testid="human-turn"]',
    },
    chatgpt: {
      input: "#prompt-textarea",
      sendBtn: '[data-testid="send-button"], button[aria-label="Send prompt"]',
      response: '[data-message-author-role="assistant"] .markdown',
      humanTurn: '[data-message-author-role="user"]',
    },
  };

  const sel = SELECTORS[SITE];

  // ── State ───────────────────────────────────────────────────────

  let lastInjectedMemoryBlock = null;   // track what we injected
  let isInjecting = false;              // prevent re-entrance
  let lastStoredTurn = "";             // prevent duplicate stores

  // ── Helpers ─────────────────────────────────────────────────────

  function getInputEl() {
    return document.querySelector(sel.input);
  }

  function getInputText(el) {
    if (!el) return "";
    return el.value !== undefined ? el.value : el.innerText || el.textContent;
  }

  function setInputText(el, text) {
    if (!el) return;
    if (el.value !== undefined) {
      // textarea
      el.value = text;
      el.dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      // contenteditable
      el.innerText = text;
      el.dispatchEvent(new InputEvent("input", { bubbles: true }));
      // Move cursor to end
      const range = document.createRange();
      const sel2 = window.getSelection();
      range.selectNodeContents(el);
      range.collapse(false);
      sel2.removeAllRanges();
      sel2.addRange(range);
    }
  }

  function sendMessage(type, payload) {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage({ type, ...payload }, (response) => {
        if (chrome.runtime.lastError) {
          console.warn("[Engram]", chrome.runtime.lastError.message);
          resolve(null);
        } else {
          resolve(response);
        }
      });
    });
  }

  function formatMemoryBlock(memories) {
    if (!memories || memories.length === 0) return "";
    const lines = memories.map((m, i) => `${i + 1}. ${m.content}`).join("\n");
    return `[Engram memories]\n${lines}\n[End of memories]\n\n`;
  }

  function showIndicator(text) {
    let el = document.getElementById("engram-indicator");
    if (!el) {
      el = document.createElement("div");
      el.id = "engram-indicator";
      el.style.cssText = [
        "position:fixed", "bottom:80px", "right:20px",
        "background:#1a1a2e", "color:#e0e0ff", "padding:8px 14px",
        "border-radius:8px", "font-size:13px", "font-family:system-ui",
        "z-index:99999", "box-shadow:0 2px 12px rgba(0,0,0,0.4)",
        "border:1px solid #3a3a6e", "transition:opacity 0.3s",
        "pointer-events:none"
      ].join(";");
      document.body.appendChild(el);
    }
    el.textContent = "🧠 " + text;
    el.style.opacity = "1";
    clearTimeout(el._hideTimer);
    el._hideTimer = setTimeout(() => { el.style.opacity = "0"; }, 3000);
  }

  // ── Memory injection (before send) ─────────────────────────────

  async function injectMemories(inputEl) {
    if (isInjecting) return;
    const query = getInputText(inputEl).trim();

    // Strip any previously injected memory block before reading the query
    const cleanQuery = query.replace(/\[Engram memories\][\s\S]*?\[End of memories\]\n\n/, "").trim();
    if (!cleanQuery) return;

    isInjecting = true;
    showIndicator("Recalling memories…");

    try {
      const response = await sendMessage("RECALL", { query: cleanQuery });
      if (!response || !response.ok || !response.data) {
        showIndicator("Engram offline");
        return;
      }

      const memories = response.data.memories || [];
      if (memories.length === 0) {
        showIndicator("No relevant memories");
        return;
      }

      // Prepend memory block to the user's message
      const memoryBlock = formatMemoryBlock(memories);
      lastInjectedMemoryBlock = memoryBlock;
      setInputText(inputEl, memoryBlock + cleanQuery);
      showIndicator(`${memories.length} memor${memories.length === 1 ? "y" : "ies"} injected`);
    } catch (e) {
      console.error("[Engram] inject error:", e);
    } finally {
      isInjecting = false;
    }
  }

  // ── Store conversation turn (after AI responds) ─────────────────

  async function storeConversationTurn() {
    // Find the last human message and last AI response
    const humanTurns = document.querySelectorAll(sel.humanTurn);
    const aiResponses = document.querySelectorAll(sel.response);

    if (!humanTurns.length || !aiResponses.length) return;

    const lastHuman = humanTurns[humanTurns.length - 1];
    const lastAI = aiResponses[aiResponses.length - 1];

    // Get text, strip the injected memory block from the human turn
    let humanText = (lastHuman.innerText || lastHuman.textContent || "").trim();
    humanText = humanText.replace(/\[Engram memories\][\s\S]*?\[End of memories\]\n\n/, "").trim();
    const aiText = (lastAI.innerText || lastAI.textContent || "").trim();

    if (!humanText || !aiText) return;

    // Build the turn content to store
    const turnContent = `User said: ${humanText}\nAssistant responded: ${aiText}`;

    // Deduplicate — don't store the same turn twice
    if (turnContent === lastStoredTurn) return;
    lastStoredTurn = turnContent;

    const response = await sendMessage("STORE", { content: turnContent });
    if (response && response.ok && response.data) {
      const stored = response.data.stored || 0;
      if (stored > 0) {
        showIndicator(`${stored} fact${stored === 1 ? "" : "s"} remembered`);
      }
    }
  }

  // ── Submit interception ─────────────────────────────────────────

  function interceptSubmit(e) {
    const inputEl = getInputEl();
    if (!inputEl) return;

    const text = getInputText(inputEl).trim();
    if (!text) return;

    // Intercept Enter (without Shift) and click on send button
    const isEnter = e.type === "keydown" && e.key === "Enter" && !e.shiftKey;
    const isClick = e.type === "click";

    if (!isEnter && !isClick) return;

    // Prevent the default send, inject memories, then allow send
    e.preventDefault();
    e.stopPropagation();

    injectMemories(inputEl).then(() => {
      // Re-dispatch the original event after injection
      if (isEnter) {
        inputEl.dispatchEvent(new KeyboardEvent("keydown", {
          key: "Enter", code: "Enter", keyCode: 13,
          bubbles: true, cancelable: true
        }));
      } else {
        const sendBtn = document.querySelector(sel.sendBtn);
        if (sendBtn) sendBtn.click();
      }
    });
  }

  // ── Response observer (watch for AI replies finishing) ──────────

  let storeTimer = null;

  function watchForResponses() {
    const observer = new MutationObserver(() => {
      // Debounce — wait 2s after last DOM change before storing
      // (AI streams tokens, we want to wait until it finishes)
      clearTimeout(storeTimer);
      storeTimer = setTimeout(storeConversationTurn, 2000);
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });
  }

  // ── Event binding (with retry for SPAs) ────────────────────────

  function bindEvents() {
    const inputEl = getInputEl();
    if (!inputEl) return false;

    // Keydown on the input box
    inputEl.addEventListener("keydown", interceptSubmit, true);

    // Also watch the send button directly
    const sendBtn = document.querySelector(sel.sendBtn);
    if (sendBtn) {
      sendBtn.addEventListener("click", interceptSubmit, true);
    }

    return true;
  }

  // SPA pages load content after the script runs — retry binding
  function tryBind(attempts = 0) {
    if (bindEvents()) {
      console.log("[Engram] Attached to", SITE);
      return;
    }
    if (attempts < 20) {
      setTimeout(() => tryBind(attempts + 1), 500);
    }
  }

  // Re-bind when URL changes (SPA navigation)
  let lastUrl = location.href;
  new MutationObserver(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      setTimeout(() => tryBind(), 500);
    }
  }).observe(document, { subtree: true, childList: true });

  // ── Init ────────────────────────────────────────────────────────

  tryBind();
  watchForResponses();

})();
