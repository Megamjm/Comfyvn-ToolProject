// VN Tools Drawer - updated for new Flask API
console.log("VN Tools initialized.");

// Utility
const api = async (path, method="GET", body=null) => {
  const opts = { method, headers:{ "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  try { return await r.json(); } catch { return {}; }
};

async function refreshGallery(filter="all") {
  const gal = document.getElementById("gallery");
  gal.innerHTML = "<p>Loading gallery...</p>";
  const data = await api("/api/gallery");
  gal.innerHTML = "";
  if (!data.ok) {
    gal.innerHTML = `<p class='error'>Failed to load gallery.</p>`;
    return;
  }
  let items = data.items;
  if (filter !== "all") items = items.filter(x => x.status === filter);

  items.forEach(it => {
    const div = document.createElement("div");
    div.className = "tile";
    const thumb = it.thumb ? `/api/thumb/${it.id}` : "";
    div.innerHTML = `
      <img src="${thumb}" alt="${it.filename}" />
      <div class="meta">
        <b>${it.filename}</b><br/>
        Status: ${it.status}
      </div>
      <div class="actions">
        <button onclick="decision('${it.id}','approve')">✅ Approve</button>
        <button onclick="decision('${it.id}','reject')">❌ Reject</button>
      </div>
    `;
    gal.appendChild(div);
  });
}

async function decision(id, action) {
  const res = await api("/api/gallery/decision", "POST", { id, action });
  if (!res.ok) alert("Failed to move image: " + (res.error || ""));
  refreshGallery();
}

// Queue render to ComfyUI
document.getElementById("queueBtn").onclick = async () => {
  const preset = document.getElementById("preset").value;
  const metaText = document.getElementById("meta").value;
  const title = document.getElementById("title").value || "Untitled";
  let meta = {};
  try { meta = JSON.parse(metaText || "{}"); } catch(e){ alert("Invalid meta JSON."); return; }
  const wfText = document.getElementById("wf").value;
  let workflow = {};
  try { workflow = JSON.parse(wfText || "{}"); } catch(e){ alert("Invalid workflow JSON."); return; }

  const payload = { title, workflow, meta };
  const res = await api("/queue", "POST", payload);
  alert(res.ok ? "Queued successfully!" : "Queue failed.");
};

// Ingest PNG manually
document.getElementById("ingestBtn").onclick = async () => {
  const id = document.getElementById("ingestId").value.trim();
  const file = document.getElementById("ingestPng").files[0];
  if (!id || !file) { alert("Missing ID or file"); return; }

  const fd = new FormData();
  fd.append("image", file);
  const r = await fetch(`/ingest/${id}`, { method:"POST", body:fd });
  const j = await r.json();
  alert(j.ok ? "Ingested successfully." : "Failed: " + j.error);
};

// Export approved renders to Ren'Py
async function exportRenpy() {
  const r = await api("/api/export_renpy", "POST");
  alert(r.ok ? "Export complete. Scenes: " + r.scenes.length : "Export failed.");
}
async function launchRenpy() {
  const r = await api("/api/launch_renpy", "POST");
  alert(r.ok ? "Ren'Py launched." : "Launch failed.");
}

// Toolbar preview button
const previewBtn = document.createElement("button");
previewBtn.textContent = "🎮 Launch VN";
previewBtn.onclick = launchRenpy;
document.querySelector("nav").appendChild(previewBtn);

// Filters
document.querySelectorAll(".filters button").forEach(b => {
  b.onclick = () => refreshGallery(b.dataset.f);
});

// Refresh
document.getElementById("refresh").onclick = () => refreshGallery();

// Theme toggle
document.getElementById("themeBtn").onclick = () => {
  document.body.classList.toggle("theme-light");
};

// Auto-refresh gallery every 15s
setInterval(refreshGallery, 15000);

// Initial load
refreshGallery();
