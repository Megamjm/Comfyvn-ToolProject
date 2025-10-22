const params = new URL(import.meta.url).searchParams;
const panelId = params.get("panel");

const lookupMount = () => {
  if (typeof window.getExtensionPanelMount === "function") {
    return window.getExtensionPanelMount(panelId);
  }
  const registry = window.__comfyExtensionMounts || {};
  return registry[panelId];
};

const mount = lookupMount();
if (!mount) {
  console.warn("[sample-hello] mount point not found for panel", panelId);
} else {
  mount.innerHTML = "";
  const intro = document.createElement("p");
  intro.textContent = "Sample Hello extension is active. Ping the /hello endpoint to see a response.";
  mount.appendChild(intro);

  const status = document.createElement("pre");
  status.className = "ext-panel-status";
  status.style.margin = "0";
  status.style.padding = "8px";
  status.style.background = "rgba(32, 48, 72, 0.35)";
  status.style.borderRadius = "6px";
  status.style.fontSize = "12px";
  status.textContent = "No request sent yet.";

  const btn = document.createElement("button");
  btn.className = "btn neutral";
  btn.textContent = "Call /hello";
  btn.style.marginTop = "8px";
  btn.onclick = async () => {
    btn.disabled = true;
    status.textContent = "Requesting…";
    try {
      const res = await fetch("/hello");
      const data = await res.json();
      status.textContent = JSON.stringify(data, null, 2);
    } catch (err) {
      status.textContent = `Request failed: ${err}`;
    } finally {
      btn.disabled = false;
    }
  };

  mount.appendChild(btn);
  const spacer = document.createElement("div");
  spacer.style.height = "8px";
  mount.appendChild(spacer);
  mount.appendChild(status);
}

