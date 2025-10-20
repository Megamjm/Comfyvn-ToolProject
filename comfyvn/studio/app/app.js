const $ = (s)=>document.querySelector(s);
const log = (o)=>{$("#log").textContent=(typeof o==="string"?o:JSON.stringify(o,null,2));};
const parseKV=(s)=>{const o={};(s||"").split("&").forEach(kv=>{if(!kv)return;const i=kv.indexOf("=");if(i<0){o[kv]=true;return;}o[kv.slice(0,i)]=decodeURIComponent(kv.slice(i+1));});return o;};

function sample(){
  return {"name":"hello","nodes":[{"id":"n1","type":"echo","params":{"message":"hello world"}}],"edges":[],"inputs":{},"outputs":{"result":"n1.result"}};
}
async function postJSON(path, body){
  const r = await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  const ct=r.headers.get("content-type")||""; return ct.includes("application/json")?await r.json():await r.text();
}
function getWF(){ try{ return JSON.parse($("#wf").value);}catch(e){ throw new Error("Invalid JSON: "+e.message);} }

$("#wf").value = JSON.stringify(sample(), null, 2);
$("#btnValidate").onclick = async ()=>{ try{ log(await postJSON("/workflows/validate", getWF())); }catch(e){ log(String(e)); } };
$("#btnSave").onclick     = async ()=>{ try{ log(await postJSON("/workflows/save", getWF())); }catch(e){ log(String(e)); } };
$("#btnRun").onclick      = async ()=>{ try{
  const wf=getWF(), args=parseKV($("#args").value);
  for(const n of (wf.nodes||[])){ if((n.type||"").toLowerCase()==="echo"){ n.params=Object.assign({},n.params||{},args); break; } }
  log(await postJSON("/workflows/instantiate", wf));
} catch(e){ log(String(e)); } };
