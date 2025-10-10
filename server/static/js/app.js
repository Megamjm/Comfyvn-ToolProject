/* ==========================================================
   VN SUITE - FRONTEND CONTROL SCRIPT (Update 1)
   Adds polling control, options menu, and persistent config
   ========================================================== */

let config = {
  polling_interval: 5,
  live_progress: true,
  auto_approve: false,
  default_vn_tier: "Simple",
  theme_mode: "Dark"
};

async function loadConfig() {
  try {
    const res = await fetch('/api/config');
    if (res.ok) config = await res.json();
    console.log('Config loaded:', config);
  } catch (err) {
    console.warn('Could not load config, using defaults.', err);
  }
}

async function saveConfig() {
  try {
    await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config)
    });
  } catch (err) {
    console.error('Failed to save config:', err);
  }
}

// Create the gear icon and menu
function createOptionsMenu() {
  const menu = document.createElement('div');
  menu.id = 'options-menu';
  menu.innerHTML = `
    <style>
      #gear-btn {
        position: fixed;
        top: 15px;
        right: 15px;
        background: #222;
        color: #eee;
        border: none;
        border-radius: 50%;
        width: 40px; height: 40px;
        font-size: 20px;
        cursor: pointer;
      }
      #options-panel {
        display: none;
        position: fixed;
        top: 60px; right: 15px;
        background: #1b1b1b;
        color: #fff;
        border: 1px solid #444;
        border-radius: 10px;
        padding: 15px;
        width: 240px;
        z-index: 9999;
      }
      #options-panel input, #options-panel select {
        width: 100%; margin-top: 6px; margin-bottom: 10px;
        background: #333; color: #fff; border: 1px solid #666;
        padding: 4px 6px; border-radius: 5px;
      }
      #options-panel label { font-size: 13px; display: block; }
    </style>

    <button id="gear-btn">⚙️</button>
    <div id="options-panel">
      <label>Polling Interval (sec)
        <input type="number" id="polling_interval" min="1" max="10" value="${config.polling_interval}">
      </label>
      <label>Live Progress
        <select id="live_progress">




/* ==========================================================
   GALLERY SYSTEM (Update 2)
   ========================================================== */

let galleryRefreshTimer;

async function loadGallery() {
  const container = document.getElementById("gallery");
  if (!container) return;
  try {
    const res = await fetch("/api/gallery");
    const images = await res.json();
    container.innerHTML = "";
    images.forEach(img => {
      const div = document.createElement("div");
      div.className = "gallery-item";
      div.innerHTML = `
        <img src="/api/gallery/${img.name}" alt="${img.name}" loading="lazy"/>
        <div class="actions">
          <button class="approve" data-file="${img.name}">✅</button>
          <button class="reject" data-file="${img.name}">❌</button>
        </div>
      `;
      container.appendChild(div);
    });

    // Bind approval/rejection
    container.querySelectorAll("button.approve, button.reject").forEach(btn => {
      btn.addEventListener("click", async () => {
        const file = btn.getAttribute("data-file");
        const decision = btn.classList.contains("approve") ? "approve" : "reject";
        await fetch("/api/gallery/decision", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filename: file, decision })
        });
        loadGallery();
      });
    });
  } catch (err) {
    console.error("Gallery load failed:", err);
  }
}

function startGalleryAutoRefresh() {
  if (galleryRefreshTimer) clearInterval(galleryRefreshTimer);
  galleryRefreshTimer = setInterval(loadGallery, 10000); // every 10 seconds
}

function createGalleryUI() {
  const galleryDiv = document.createElement("div");
  galleryDiv.id = "gallery";
  galleryDiv.innerHTML = `<p style="color:#aaa;">Loading gallery...</p>`;
  document.body.appendChild(galleryDiv);

  const style = document.createElement("style");
  style.textContent = `
    #gallery {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 10px; padding: 60px 10px 10px;
    }
    .gallery-item {
      position: relative;
      border: 1px solid #333;
      border-radius: 8px;
      overflow: hidden;
      background: #111;
    }
    .gallery-item img {
      width: 100%; height: auto; display: block;
    }
    .actions {
      position: absolute; bottom: 5px; right: 5px;
    }
    .actions button {
      background: #222; border: none; color: #fff;
      border-radius: 5px; margin-left: 4px;
      cursor: pointer; font-size: 16px;
    }
  `;
  document.head.appendChild(style);

  loadGallery();
  startGalleryAutoRefresh();
}

// Initialize gallery after config and options menu
window.addEventListener("DOMContentLoaded", async () => {
  await loadConfig();
  createOptionsMenu();
  startPolling();
  createGalleryUI();
});

/* ==========================================================
   UPDATE 3 – COMFYUI SYNC + LLM SUMMARY + RPY EXPORT
   ========================================================== */

async function syncComfyUI() {
  const btn = document.getElementById("sync-btn");
  btn.textContent = "Syncing...";
  const res = await fetch("/api/sync/comfyui");
  const data = await res.json();
  btn.textContent = `Synced ${data.synced.length} new`;
  loadGallery();
}

async function generateSummary(filename) {
  const res = await fetch("/api/summary", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename })
  });
  const data = await res.json();
  alert(`Summary:\n${data.summary}`);
}

async function exportToQueue(filename) {
  const res = await fetch("/api/export_queue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename })
  });
  const data = await res.json();
  alert(`Added to Ren'Py queue: Scene ID ${data.scene_id}`);
}

// Modify gallery to include new buttons
function addVNTools() {
  const toolbar = document.createElement("div");
  toolbar.id = "vn-toolbar";
  toolbar.innerHTML = `
    <style>
      #vn-toolbar {
        position: fixed;
        top: 10px; left: 15px;
        background: #111;
        color: #fff;
        padding: 8px 12px;
        border-radius: 8px;
        border: 1px solid #444;
        z-index: 10000;
      }
      #vn-toolbar button {
        margin-right: 6px;
        background: #222;
        color: #fff;
        border: none;
        padding: 5px 10px;
        border-radius: 6px;
        cursor: pointer;
      }
    </style>
    <button id="sync-btn">🔄 Sync ComfyUI</button>
  `;
  document.body.appendChild(toolbar);
  document.getElementById("sync-btn").onclick = syncComfyUI;

  // Patch gallery load buttons
  const origLoad = loadGallery;
  loadGallery = async function () {
    await origLoad();
    document.querySelectorAll(".gallery-item").forEach(div => {
      const file = div.querySelector("img").getAttribute("alt");
      const actions = div.querySelector(".actions");
      const sumBtn = document.createElement("button");
      sumBtn.textContent = "🧠";
      sumBtn.title = "Generate summary";
      sumBtn.onclick = () => generateSummary(file);

      const exportBtn = document.createElement("button");
      exportBtn.textContent = "📦";
      exportBtn.title = "Add to VN export queue";
      exportBtn.onclick = () => exportToQueue(file);

      actions.appendChild(sumBtn);
      actions.appendChild(exportBtn);
    });
  };
}

window.addEventListener("DOMContentLoaded", async () => {
  await loadConfig();
  createOptionsMenu();
  startPolling();
  createGalleryUI();
  addVNTools();
});

/* ==========================================================
   UPDATE 4 – REN'PY EXPORTER
   ========================================================== */

async function exportRenpy() {
  const btn = document.getElementById("renpy-btn");
  btn.textContent = "Exporting...";
  const res = await fetch("/api/export_renpy", { method: "POST" });
  const data = await res.json();
  btn.textContent = `Exported ${data.exported.length}`;
  if (data.exported.length === 0) alert("No new scenes to export.");
  else alert(`Exported scenes:\n${data.exported.join("\n")}`);
}

function addRenpyButton() {
  const toolbar = document.getElementById("vn-toolbar");
  const btn = document.createElement("button");
  btn.id = "renpy-btn";
  btn.textContent = "🎮 Export to Ren'Py";
  btn.onclick = exportRenpy;
  toolbar.appendChild(btn);
}

window.addEventListener("DOMContentLoaded", async () => {
  await loadConfig();
  createOptionsMenu();
  startPolling();
  createGalleryUI();
  addVNTools();
  addRenpyButton();
});


async function launchRenpy() {
  alert("Launching Ren'Py...");
  await fetch("/api/launch_renpy", { method: "POST" });
}

function addRenpyButton() {
  const toolbar = document.getElementById("vn-toolbar");
  const btnExport = document.createElement("button");
  btnExport.id = "renpy-btn";
  btnExport.textContent = "🎮 Export to Ren'Py";
  btnExport.onclick = exportRenpy;
  toolbar.appendChild(btnExport);

  const btnPlay = document.createElement("button");
  btnPlay.id = "play-vn";
  btnPlay.textContent = "▶️ Play VN";
  btnPlay.onclick = launchRenpy;
  toolbar.appendChild(btnPlay);
}
