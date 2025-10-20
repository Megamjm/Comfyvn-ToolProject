
(async function(){
  async function j(url, opt){ const r=await fetch(url, opt); try{ return await r.json(); }catch{return {};}}
  const panels = [
    {id:"panel-left", urls:["/analyze/scan","/i18n/export","/continuity/validate"]},
    {id:"panel-center", urls:["/branchmap/build","/replay/auto","/music/mood"]},
    {id:"panel-right", urls:["/voice/speak","/play3d/status","/market/list"]}
  ];
  console.log("Studio v2 ready", await j("/diagnostics/summary").catch(()=>({})), panels);
})();
