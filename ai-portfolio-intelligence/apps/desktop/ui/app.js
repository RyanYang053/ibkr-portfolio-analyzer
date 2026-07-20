function getRuntime() {
  const runtime = window.__DESKTOP_RUNTIME__;
  if (!runtime || !runtime.apiBaseUrl || !runtime.sessionToken) {
    throw new Error("Desktop runtime is unavailable");
  }
  return runtime;
}

async function localFetch(path, init = {}) {
  const runtime = getRuntime();
  const headers = new Headers(init.headers || {});
  headers.set("X-Local-Session", runtime.sessionToken);
  return fetch(`${runtime.apiBaseUrl}${path}`, { ...init, headers });
}

function showView(name) {
  document.querySelectorAll(".view").forEach((el) => el.classList.remove("active"));
  document.querySelectorAll(".nav button").forEach((el) => el.classList.remove("active"));
  document.getElementById(`view-${name}`).classList.add("active");
  document.querySelector(`.nav button[data-view="${name}"]`).classList.add("active");
}

async function refreshStatus() {
  const box = document.getElementById("status-box");
  try {
    const health = await fetch(`${getRuntime().apiBaseUrl}/health`);
    const healthJson = await health.json();
    const status = await localFetch("/desktop/status");
    const statusJson = await status.json();
    box.textContent = JSON.stringify({ health: healthJson, desktop: statusJson }, null, 2);
  } catch (error) {
    box.textContent = error instanceof Error ? error.message : String(error);
  }
}

async function createExport() {
  const box = document.getElementById("export-box");
  box.textContent = "Creating export…";
  try {
    const response = await localFetch("/desktop/export", { method: "POST" });
    const payload = await response.json();
    box.textContent = JSON.stringify(payload, null, 2);
  } catch (error) {
    box.textContent = error instanceof Error ? error.message : String(error);
  }
}

document.querySelectorAll(".nav button").forEach((button) => {
  button.addEventListener("click", () => {
    const view = button.getAttribute("data-view");
    showView(view);
    if (view === "status") {
      refreshStatus();
    }
  });
});

document.getElementById("export-btn").addEventListener("click", createExport);

// Best-effort status prefetch once runtime is injected.
const timer = setInterval(() => {
  try {
    getRuntime();
    refreshStatus();
    clearInterval(timer);
  } catch (_error) {
    // Runtime injects during window setup.
  }
}, 250);
