const apiInput  = document.getElementById("api-base");
const userInput = document.getElementById("user-id");
const toggle    = document.getElementById("enabled-toggle");
const saveBtn   = document.getElementById("save-btn");
const saveMsg   = document.getElementById("save-msg");
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");

// Load saved settings
chrome.storage.sync.get(
  { apiBase: "http://localhost:8000", userId: "default", enabled: true },
  (cfg) => {
    apiInput.value  = cfg.apiBase;
    userInput.value = cfg.userId;
    toggle.checked  = cfg.enabled;
    checkHealth(cfg.apiBase);
  }
);

async function checkHealth(base) {
  try {
    const resp = await fetch(`${base}/health`, { signal: AbortSignal.timeout(3000) });
    if (resp.ok) {
      statusDot.className   = "dot online";
      statusText.textContent = "API online";
    } else {
      throw new Error();
    }
  } catch {
    statusDot.className   = "dot offline";
    statusText.textContent = "API offline — is uvicorn running?";
  }
}

saveBtn.addEventListener("click", () => {
  const cfg = {
    apiBase: apiInput.value.replace(/\/$/, ""),
    userId:  userInput.value.trim() || "default",
    enabled: toggle.checked,
  };
  chrome.storage.sync.set(cfg, () => {
    saveMsg.textContent = "Saved ✓";
    setTimeout(() => { saveMsg.textContent = ""; }, 2000);
    checkHealth(cfg.apiBase);
  });
});

apiInput.addEventListener("change", () => checkHealth(apiInput.value));
