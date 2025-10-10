async function fetchText(url){ const r = await fetch(url); return await r.text(); }
async function fetchJSON(url){ const r = await fetch(url); return await r.json(); }
function el(html){ const t=document.createElement('template'); t.innerHTML=html.trim(); return t.content.firstChild; }

const presetSel = document.getElementById('preset');
const wfArea = document.getElementById('wf');
const metaArea = document.getElementById('meta');
const titleInp = document.getElementById('title');
const galleryDiv = document.getElementById('gallery');
const tagFilter = document.getElementById('tagFilter');

async function loadPreset(){
  const url = presetSel.value;
  try{
    const txt = await fetchText(url);
    wfArea.value = txt;
  }catch(e){
    wfArea.value = `/* Failed to load preset: ${e} */`;
  }
}
presetSel.addEventListener('change', loadPreset);
loadPreset();

document.getElementById('queueBtn').onclick = async () => {
  let wf;
  try{ wf = JSON.parse(wfArea.value); } catch(e){ alert("Workflow JSON invalid: "+e); return; }
  let meta = {}; 
  if(metaArea.value.trim()){
    try{ meta = JSON.parse(metaArea.value); } catch(e){ alert("Meta JSON invalid: "+e); return; }
  }
  const res = await fetch('/queue', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({title: titleInp.value||'untitled', workflow: wf, meta})});
  const j = await res.json();
  if(!res.ok){ alert("Queue failed: "+JSON.stringify(j)); return; }
  alert("Queued: "+j.id);
  refresh();
};

async function refresh(filter){
  const params = new URLSearchParams();
  if(filter && filter!=="all") params.set("status", filter);
  if(tagFilter.value) params.set("tag", tagFilter.value);
  const j = await fetchJSON('/gallery?'+params.toString());
  galleryDiv.innerHTML = "";
  for(const a of j){
    const thumb = a.png_path ? `<img class="thumb" src="/static/${a.png_path.split('static/').pop()}" onerror="this.style.display='none'"/>` : `<div class="thumb"></div>`;
    const card = el(`<div class="card">
      ${thumb}
      <div class="info">
        <div><b>${a.title||'untitled'}</b></div>
        <div>Status: ${a.status}</div>
        <div><small>${a.id}</small></div>
        <div class="row">
          <button data-a="approve" data-id="${a.id}">Approve</button>
          <button data-a="reject" data-id="${a.id}">Reject</button>
        </div>
      </div>
    </div>`);
    card.querySelectorAll('button').forEach(btn=>{
      btn.onclick = async () => {
        const action = btn.dataset.a;
        const res = await fetch(`/${action}/${btn.dataset.id}`, {method:'POST'});
        if(res.ok) refresh(filter);
      };
    });
    galleryDiv.appendChild(card);
  }
}
document.getElementById('refresh').onclick = ()=> refresh(document.querySelector('.filters .active')?.dataset.f);
document.querySelectorAll('.filters button').forEach(b=>{
  b.onclick = ()=>{
    document.querySelectorAll('.filters button').forEach(x=>x.classList.remove('active'));
    b.classList.add('active'); refresh(b.dataset.f);
  };
});
refresh("all");

document.getElementById('ingestBtn').onclick = async () => {
  const id = document.getElementById('ingestId').value.trim();
  const file = document.getElementById('ingestPng').files[0];
  if(!id || !file) { alert("Provide asset id and PNG file"); return; }
  const fd = new FormData();
  fd.append('image', file);
  const res = await fetch(`/ingest/${id}`, {method:'POST', body:fd});
  const j = await res.json();
  if(!res.ok){ alert("Ingest failed: "+JSON.stringify(j)); return; }
  alert("Ingested.");
  refresh();
};

document.getElementById('themeBtn').onclick = ()=>{
  const b = document.body;
  if(b.classList.contains('theme-default')) b.classList.replace('theme-default','theme-sakura');
  else if(b.classList.contains('theme-sakura')) b.classList.replace('theme-sakura','theme-neon');
  else b.classList.replace('theme-neon','theme-default');
};
