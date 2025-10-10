const api = path => fetch(path).then(r => r.json());

async function refreshGallery(){
  const res = await api("/api/gallery");
  const gal = document.getElementById("gallery");
  gal.innerHTML = "";
  res.items.forEach(it => {
    const div = document.createElement("div");
    div.className = "tile " + it.status;
    div.innerHTML = `
      <img src="/api/thumb/${it.id}" alt="${it.filename}">
      <div class="meta">${it.filename}</div>
      <button onclick="decision('${it.id}','approve')">✅</button>
      <button onclick="decision('${it.id}','reject')">❌</button>
    `;
    gal.appendChild(div);
  });
}

async function decision(id, action){
  await fetch("/api/gallery/decision",{
    method:"POST",
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id,action})
  });
  refreshGallery();
}

async function updateStatus(){
  const s = await api("/api/status");
  const sb = document.getElementById("statusbar");
  sb.textContent = `🕒 ${s.time} | ComfyUI: ${s.comfyui_ok?'✅':'❌'} | Approved: ${s.approved} | Pending: ${s.pending}`;
}
setInterval(updateStatus, 5000);

refreshGallery();
updateStatus();
