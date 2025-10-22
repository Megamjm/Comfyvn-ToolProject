// comfyvn/studio/app.js – Phase 4.8 UI
(() => {
  const $ = (id) => document.getElementById(id);

  const wf = $("wf");
  const btnValidate = $("btnValidate");
  const btnSave = $("btnSave");
  const btnRun = $("btnRun");
  const btnBundle = $("btnBundle");
  const btnPop = $("btnPop");
  const btnJsonPop = $("btnJsonPop");
  const btnJsonCopy = $("btnJsonCopy");
  const args = $("args");

  const sceneName = $("sceneName");
  const sceneTitle = $("sceneTitle");
  const sceneBg = $("sceneBg");
  const sceneMusic = $("sceneMusic");
  const sceneSprites = $("sceneSprites");

  const lineSpeaker = $("lineSpeaker");
  const lineText = $("lineText");
  const btnAddLine = $("btnAddLine");
  const btnClearLines = $("btnClearLines");
  const linesTable = document.querySelector("#linesTable tbody");
  const extensionsCard = $("extensionsCard");
  const extensionsBody = $("extensionsBody");
  const extensionMounts = Object.create(null);
  window.__comfyExtensionMounts = extensionMounts;
  window.getExtensionPanelMount = (panelId) => extensionMounts[panelId] || null;

  // preview
  const bgImg = $("bgImg");
  const spritesDiv = document.getElementById("sprites");
  const audio = $("audio");
  const hud = $("hud");

  const LS_KEY = "comfyvn_studio_state_v3";
  let state = { name:"intro_scene", title:"Intro", background:"", music:"", sprites:[], lines:[] };

  function spritesFromInput(v){ return (v||"").split(",").map(s=>s.trim()).filter(Boolean); }
  function spritesToInput(a){ return (a||[]).join(","); }

  function logJSON(obj){
    // minimal console log; UI remains clean
    try{ console.log(obj); }catch{}
  }

  function renderLines(){
    linesTable.innerHTML = "";
    state.lines.forEach((ln, idx) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${ln.speaker||""}</td><td>${ln.text||""}</td><td></td>`;
      const del = document.createElement("button");
      del.textContent = "Delete";
      del.className = "btn neutral";
      del.onclick = () => { state.lines.splice(idx,1); renderLines(); renderJSON(); persist(); renderPreview(); };
      tr.lastChild.appendChild(del);
      linesTable.appendChild(tr);
    });
  }

  function renderPreview(){
    bgImg.src = state.background || "";
    hud.textContent = `${state.title || state.name || "Preview"}`;
    spritesDiv.innerHTML = "";
    const N = Math.max(1, (state.sprites||[]).length);
    (state.sprites||[]).forEach((src,i)=>{
      const img = document.createElement("img");
      img.className = "sprite";
      img.style.left = `${((i+1)/(N+1))*100}%`;
      img.src = src;
      spritesDiv.appendChild(img);
    });
    try{ audio.src = state.music || ""; if(!state.music) audio.pause(); }catch{}
  }

  function renderJSON(){ wf.value = JSON.stringify(state, null, 2); }
  function persist(){ try{ localStorage.setItem(LS_KEY, JSON.stringify(state)); }catch{} }
  function restore(){ try{ const t=localStorage.getItem(LS_KEY); if(t) state = JSON.parse(t); }catch{} }

  function syncFromForm(){
    state.name = (sceneName.value||"draft").trim();
    state.title = (sceneTitle.value||"").trim();
    state.background = (sceneBg.value||"").trim();
    state.music = (sceneMusic.value||"").trim();
    state.sprites = spritesFromInput(sceneSprites.value);
    renderLines(); renderJSON(); renderPreview(); persist();
    return JSON.parse(wf.value);
  }
  function syncFormToState(){
    sceneName.value = state.name||"draft";
    sceneTitle.value = state.title||"";
    sceneBg.value = state.background||"";
    sceneMusic.value = state.music||"";
    sceneSprites.value = spritesToInput(state.sprites);
    renderLines(); renderJSON(); renderPreview();
  }

  function parseArgs(qs){
    const out={}; for(const kv of (qs||"").split("&")){ const [k,v]=kv.split("="); if(!k) continue; out[decodeURIComponent(k)] = decodeURIComponent(v||""); }
    return out;
  }
  async function post(path, body){
    const res = await fetch(path, { method:"POST", headers:{ "Content-Type":"application/json" }, body: JSON.stringify(body||{}) });
    let js={}; try{ js=await res.json(); }catch{}
    logJSON(js); return js;
  }

  async function loadExtensionPanels(){
    if(!extensionsCard || !extensionsBody) return;
    try{
      const res = await fetch("/api/extensions/ui/panels");
      if(!res.ok) return;
      let payload = {};
      try{ payload = await res.json(); }catch{ payload = {}; }
      const panels = Array.isArray(payload.panels) ? payload.panels : [];
      if(!panels.length) return;
      extensionsCard.hidden = false;
      panels.forEach((panel, idx) => {
        const pluginId = panel.plugin_id || panel.id || "extension";
        if(!pluginId) return;
        const panelId = `${pluginId}:${idx}`;
        if(extensionMounts[panelId]) return;

        const wrapper = document.createElement("div");
        wrapper.className = "ext-panel";
        wrapper.dataset.pluginId = pluginId;
        wrapper.dataset.panelSlot = panel.slot || "";

        const header = document.createElement("h4");
        header.textContent = panel.label || pluginId || "Extension Panel";
        wrapper.appendChild(header);

        const mount = document.createElement("div");
        mount.className = "ext-panel-mount";
        wrapper.appendChild(mount);

        extensionMounts[panelId] = mount;
        extensionsBody.appendChild(wrapper);

        const script = document.createElement("script");
        script.type = "module";
        script.src = `/api/extensions/${encodeURIComponent(pluginId)}/ui/${panel.path}?panel=${encodeURIComponent(panelId)}`;
        script.dataset.pluginId = pluginId;
        script.dataset.panelId = panelId;
        script.onerror = () => {
          mount.textContent = "Failed to load extension panel.";
        };
        document.body.appendChild(script);
      });
    }catch(err){
      console.warn("[extensions] load failure", err);
    }
  }

  // inputs wire-up
  [sceneName,sceneTitle,sceneBg,sceneMusic,sceneSprites].forEach(el => el.oninput = syncFromForm);

  btnAddLine.onclick = () => {
    const s=lineSpeaker.value.trim(), t=lineText.value.trim();
    if(!t) return;
    state.lines.push({speaker:s, text:t});
    lineText.value="";
    renderLines(); renderJSON(); renderPreview(); persist();
  };
  btnClearLines.onclick = () => { state.lines = []; renderLines(); renderJSON(); renderPreview(); persist(); };

  btnValidate.onclick = async () => {
    const payload = syncFromForm(); const extra = parseArgs(args.value||"");
    await post("/workflows/validate", { ...payload, ...extra });
  };
  btnSave.onclick = async () => {
    const payload = syncFromForm(); const extra = parseArgs(args.value||"");
    const merged = { ...payload, ...extra }; const name = merged.name || "draft";
    await post(`/workflows/put/${encodeURIComponent(name)}`, merged);
  };
  btnRun.onclick = async () => {
    const payload = syncFromForm(); const extra = parseArgs(args.value||"");
    const merged = { ...payload, ...extra };
    let js = await post("/workflows/instantiate", merged);
    if (!js?.ok) js = await post("/workflows/templates/instantiate/", merged);
  };
  btnBundle.onclick = async () => {
    const js = await post("/export/bundle/renpy", {});
    if(js?.ok && js.zip){ logJSON({download: js.zip}); }
  };

  // pop-outs
  btnPop.onclick = () => {
    const w = window.open("", "_blank", "width=900,height=700");
    if(!w) return;
    const html = `
      <html><head><title>ComfyVN Preview</title><link rel="stylesheet" href="/studio/theme.css"></head>
      <body style="padding:12px">
        <div class="card" style="height:calc(100vh - 24px)">
          <h3 class="header" style="position:static">Preview – ${state.title||state.name}</h3>
          <div class="body" style="padding:0; height:100%">
            <div class="stage" style="height:calc(100% - 58px)">
              <img id="bg" style="position:absolute; inset:0; width:100%; height:100%; object-fit:cover">
              <div id="sp"></div>
              <div class="hud" id="h"></div>
              <audio id="au" controls style="position:absolute;left:10px;bottom:10px;width:260px"></audio>
            </div>
          </div>
        </div>
        <script>
          const S = ${JSON.stringify(state)};
          const bg=document.getElementById('bg'), sp=document.getElementById('sp'), au=document.getElementById('au'), h=document.getElementById('h');
          bg.src = S.background||""; h.textContent = S.title||S.name||"Preview";
          sp.innerHTML=""; const N=Math.max(1,(S.sprites||[]).length);
          (S.sprites||[]).forEach((src,i)=>{ const img=document.createElement('img'); img.className='sprite'; img.style.left=((i+1)/(N+1))*100+'%'; img.src=src; sp.appendChild(img); });
          try{ au.src = S.music||""; }catch(e){}
        </script>
      </body></html>`;
    w.document.open(); w.document.write(html); w.document.close();
  };

  btnJsonPop.onclick = () => {
    const w = window.open("", "_blank");
    if(!w) return;
    w.document.open();
    w.document.write(`<pre style="white-space:pre-wrap;font-family:var(--mono);padding:16px;background:#0c0f14;color:#e8ecf6">${wf.value.replace(/[&<>]/g, s=>({ "&":"&amp;","<":"&lt;",">":"&gt;"}[s]))}</pre>`);
    w.document.close();
  };
  btnJsonCopy.onclick = async () => {
    try{ await navigator.clipboard.writeText(wf.value); }catch{}
  };

  // keep args reflecting inputs
  setInterval(() => {
    args.value = `name=${encodeURIComponent(sceneName.value||"draft")}`+
                 `&title=${encodeURIComponent(sceneTitle.value||"")}`+
                 `&background=${encodeURIComponent(sceneBg.value||"")}`+
                 `&music=${encodeURIComponent(sceneMusic.value||"")}`+
                 `&sprites=${encodeURIComponent(sceneSprites.value||"")}`;
  }, 500);

  // init
  (function init(){
    restore();
    if(!state.name) state.name="intro_scene";
    if(!Array.isArray(state.lines)) state.lines=[];
    syncFormToState();
  })();

  loadExtensionPanels();
})();
