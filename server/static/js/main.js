// VN Tools Drawer - updated for new Flask API
console.log("VN Tools initialized.");

// Show logout link if session exists
fetch("/api/config").then(r=>r.json()).then(cfg=>{
  if(cfg.VN_AUTH===true || cfg.VN_AUTH==="1"){
    document.getElementById("logoutLink").style.display="inline-block";
  }
});


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

// -----------------------------
// Tabs
// -----------------------------
document.querySelectorAll("nav button").forEach(btn=>{
  btn.onclick=()=>{
    document.querySelectorAll("nav button").forEach(b=>b.classList.remove("active"));
    document.querySelectorAll(".tab").forEach(t=>t.classList.remove("active"));
    btn.classList.add("active");
    const id=btn.id.replace("tab-","");
    document.getElementById(id+"Tab").classList.add("active");
  };
});

// -----------------------------
// Config Editor
// -----------------------------
async function loadConfig(){
  const form=document.getElementById("configForm");
  const cfg=await api("/api/config");
  form.innerHTML="";
  Object.entries(cfg).forEach(([k,v])=>{
    const row=document.createElement("div");
    row.className="cfgrow";
    row.innerHTML=`<label>${k}</label>
      <input id="cfg-${k}" value="${v}"/>`;
    form.appendChild(row);
  });
}

async function saveConfig(){
  const inputs=document.querySelectorAll("#configForm input");
  const data={};
  inputs.forEach(i=>{
    let val=i.value;
    if(!isNaN(val)) val=Number(val);
    if(val==="true") val=true;
    if(val==="false") val=false;
    data[i.id.replace("cfg-","")]=val;
  });
  const r=await api("/api/config","POST",data);
  alert(r.ok?"Config saved — reload to apply.":"Save failed.");
}

// -----------------------------
// Sync + Status
// -----------------------------
async function syncComfy(){
  const r=await api("/api/sync/comfyui","POST");
  alert(r.ok?`Imported ${r.imported.length} files.`:"Sync failed.");
  refreshGallery();
}

async function updateStatus(){
  const s=await api("/health");
  const sb=document.getElementById("statusbar");
  sb.textContent=`🕒 ${s.time} | ComfyUI: ${s.comfyui_ok?'✅':'❌'}`;
}

// -----------------------------
// Export / Launch
// -----------------------------
document.getElementById("exportBtn").onclick=async()=>{
  const r=await api("/api/export_renpy","POST");
  alert(r.ok?"Exported to Ren’Py.":"Export failed.");
};
document.getElementById("launchBtn").onclick=async()=>{
  const r=await api("/api/launch_renpy","POST");
  alert(r.ok?"Launched Ren’Py.":"Launch failed.");
};

// -----------------------------
// Bindings
// -----------------------------
document.getElementById("syncBtn").onclick=syncComfy;
document.getElementById("refresh").onclick=refreshGallery;
document.getElementById("saveConfig").onclick=saveConfig;

// -----------------------------
// Init
// -----------------------------
loadConfig();
refreshGallery();
updateStatus();

// auto-sync interval (from config poll_interval_seconds)
let pollInterval=5000;
api("/api/config").then(cfg=>{
  pollInterval=(cfg.poll_interval_seconds||5)*1000;
  setInterval(()=>{updateStatus();syncComfy();},pollInterval);
});

// -----------------------------
// THEME SWITCHING
// -----------------------------
const themeSelect=document.getElementById("themeSelect");
themeSelect.onchange=()=>{
  document.body.className=themeSelect.value;
  api("/api/config","POST",{theme_mode:themeSelect.value});
};

// Load theme from config
api("/api/config").then(cfg=>{
  const mode=cfg.theme_mode||"theme-dark";
  document.body.className=mode;
  themeSelect.value=mode;
});

// -----------------------------
// LIVE RENDER MONITOR
// -----------------------------
let renderState={jobs:0,progress:0};

async function pollRenderStatus(){
  try{
    const h=await api("/health");
    const gal=await api("/api/gallery");
    const bar=document.getElementById("progressFill");
    const text=document.getElementById("statusText");

    // heuristic: if new items appeared in gallery, show “rendering” briefly
    renderState.jobs = (gal.items||[]).filter(x=>x.status==="pending").length;
    renderState.progress = renderState.jobs>0 ? Math.min(100,renderState.jobs*20) : 100;

    bar.style.width = renderState.progress + "%";
    if(renderState.jobs>0){
      text.textContent=`Rendering ${renderState.jobs} job${renderState.jobs>1?'s':''}...`;
      bar.style.background="#3af";
    } else {
      text.textContent=`Idle — ComfyUI ${h.comfyui_ok?'✅ Online':'❌ Offline'}`;
      bar.style.background="#4a4";
    }
  }catch(e){
    console.warn("Poll failed:",e);
  }
}
setInterval(pollRenderStatus,4000);

@app.get("/api/render_state")
def api_render_state();
    """Placeholder ComfyUI render monitor."""
    try:
        outputs = list(Path(CONFIG.get("comfyui_output_dir")).glob("*.png"))
        return jsonify({
            "ok": True,
            "active_jobs": 0,
            "outputs": len(outputs),
            "last_output": outputs[-1].name if outputs else None
        })
    except Exception:
        return jsonify({"ok": False})
