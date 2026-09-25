/* Holistic interpretation feedback is separate from preference and model accuracy. */
(() => {
  const r=contextReport, el=id=>document.getElementById(id), key='taste-context:'+r.report_id;
  let draft={assessment:'未评价',note:''}, url;
  try { const saved=JSON.parse(localStorage.getItem(key)||'null');
    if(saved && ['未评价','有','部分有','没有'].includes(saved.assessment) && typeof saved.note==='string' && saved.note.length<=2000) draft=saved;
  } catch { el('context-status').textContent='草稿恢复失败，可直接填写并导出。'; }
  const buttons=[];
  function update(){buttons.forEach(b=>b.setAttribute('aria-pressed',String(b.textContent===draft.assessment)));}
  function persist(){update();try{localStorage.setItem(key,JSON.stringify(draft));el('context-status').textContent='草稿已保存在当前浏览器；点击保存写入本机。';}catch{el('context-status').textContent='草稿不可用，请保存或导出备份。';}}
  for(const value of ['有','部分有','没有']){
    const b=document.createElement('button');b.textContent=value;b.onclick=()=>{draft.assessment=value;persist();};buttons.push(b);el('context-ratings').append(b);
  }
  const reset=document.createElement('button');reset.textContent='撤销评价';reset.onclick=()=>{draft.assessment='未评价';persist();};el('context-ratings').append(reset);
  el('context-note').value=draft.note;el('context-note').oninput=()=>{draft.note=el('context-note').value;persist();};update();
  el('context-save').onclick=async()=>{
    const payload={schema_version:1,kind:'context_interpretation',report_id:r.report_id,source_sha256:r.source_sha256,listening_range:r.listening_range,liked_range:r.liked_range,...draft};
    const text=JSON.stringify(payload,null,2);el('context-json').value=text;
    if(url)URL.revokeObjectURL(url);url=URL.createObjectURL(new Blob([text],{type:'application/json'}));
    const a=el('context-download');a.href=url;a.download='context-feedback.json';a.hidden=false;
    el('context-status').textContent='备份已准备好，可下载或复制。';
    if(location.protocol!=='http:'||location.hostname!=='127.0.0.1')return;
    el('context-save').disabled=true;
    try{const response=await fetch('/__context_feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:text});if(!response.ok)throw new Error('HTTP '+response.status);
      const saved=await response.json();a.href=saved.url;a.download=saved.file;el('context-status').textContent='已保存到本机 listening-exports/'+saved.file;
    }catch(e){el('context-status').textContent='本机保存未完成：'+e.message+'。请展开导出备份。';}finally{el('context-save').disabled=false;}
  };
  window.addEventListener('pagehide',()=>{if(url)URL.revokeObjectURL(url);});
})();
