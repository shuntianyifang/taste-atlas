/* Interval annotations stay local. Model candidates and personal reactions remain separate. */
(() => {
  const el = id => document.getElementById(id);
  const t = fragments.track;
  const key = 'taste-fragments:' + fragments.report_id + ':' + t.slug;
  const fields = ['reaction','description_match','separation_quality','layer','reason'];
  const defaults = c => ({id:c.id,source_sha256:c.source_sha256,start:c.start,end:c.end,
    reaction:'未评价',description_match:'未核对',separation_quality:'未核对',layer:'',reason:''});
  let rows = t.fragments.map(defaults), storageAvailable = true;
  try {
    const saved = JSON.parse(localStorage.getItem(key) || 'null');
    if (Array.isArray(saved)) rows = rows.map(row => {
      const previous = saved.find(x => x.id === row.id && x.source_sha256 === row.source_sha256 && x.start === row.start && x.end === row.end);
      if (previous) for (const f of fields) if (typeof previous[f] === 'string') row[f] = previous[f];
      return row;
    });
  } catch { storageAvailable = false; }
  function text(parent, tag, value) { const node=document.createElement(tag);node.textContent=value;parent.append(node);return node; }
  function playButton(parent, label, start, end) {
    const b=text(parent,'button',label);b.onclick=()=>document.dispatchEvent(new CustomEvent('taste-play-interval',{detail:{start,end}}));
  }
  function compare() {
    const box=el('preference-pairs');box.replaceChildren();let count=0;
    for(let i=0;i<rows.length;i++) for(let j=i+1;j<rows.length;j++) {
      if(rows[i].reaction==='未评价'||rows[j].reaction==='未评价')continue;
      const a=t.fragments[i],b=t.fragments[j],shared=a.features.filter(x=>b.features.includes(x));
      if(!shared.length)continue;
      count++;
      const p=text(box,'p',`${a.id}（${rows[i].reaction}）与 ${b.id}（${rows[j].reaction}）：有 ${shared.length} 个同模型候选线索重合。${rows[i].reaction!==rows[j].reaction?'反应不同，值得比较声音层和上下文。':'反应相同，可继续检查是否由同一声音吸引你。'}共同候选不证明偏好原因。`);
      playButton(p,'听 A',a.start,a.end);playButton(p,'听 B',b.start,b.end);
    }
    if(!count)text(box,'p','至少评价两个有共同候选线索的片段后，显示复听对照；未评价不会算作无感。');
  }
  function changed() {
    try { localStorage.setItem(key,JSON.stringify(rows));el('feedback-status').textContent='草稿已保存在当前浏览器；点击保存可导出本机文件。'; }
    catch { storageAvailable=false;el('feedback-status').textContent='浏览器草稿存储不可用，请点击保存或复制 JSON。'; }
    compare();
  }
  const cards=[];
  let active=Math.max(0,rows.findIndex(r=>r.reaction==='未评价'));
  function showCard() {
    cards.forEach((card,i)=>card.hidden=i!==active);
    el('fragment-progress').textContent=`片段 ${active+1} / ${cards.length} · 已记录 ${rows.filter(r=>r.reaction!=='未评价').length} 段`;
    el('previous-fragment').disabled=active===0;
    el('next-fragment').disabled=active===cards.length-1;
  }
  for(const [index,c] of t.fragments.entries()) {
    const card=text(el('fragment-cards'),'article','');card.style.cssText='border-top:1px solid #52708a;padding:18px 0';
    cards.push(card);
    const stamp=s=>`${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,'0')}`;
    text(card,'h2',`先听这 ${Math.round(c.end-c.start)} 秒`);
    text(card,'p',`原曲 ${stamp(c.start)}–${stamp(c.end)}。不用分析音乐，先留意自己想不想继续听。`);
    playButton(card,'▶ 播放这一段',c.start,c.end);
    const pause=text(card,'button','暂停');pause.onclick=()=>el('pause').click();
    const reactionBox=text(card,'div','');text(reactionBox,'h3','这段给你的感觉？');
    const reactionButtons=[];
    for(const reaction of ['喜欢','无感','不喜欢']) {
      const b=text(reactionBox,'button',reaction);reactionButtons.push(b);
      b.setAttribute('aria-pressed',String(rows[index].reaction===reaction));
      b.onclick=()=>{rows[index].reaction=reaction;reactionButtons.forEach(x=>x.setAttribute('aria-pressed',String(x===b)));changed();showCard();};
    }
    const undo=text(reactionBox,'button','撤销选择');undo.onclick=()=>{rows[index].reaction='未评价';reactionButtons.forEach(x=>x.setAttribute('aria-pressed','false'));changed();showCard();};
    const optional=text(card,'details','');text(optional,'summary','想补充一句？（可跳过）');
    const details=text(card,'details','');text(details,'summary','想知道这里发生了什么？');
    playButton(details,'听变化前',c.start,c.boundary);playButton(details,'听变化后',c.boundary,c.end);
    text(details,'p','观察：'+c.observation);text(details,'p','听感假设：'+c.interpretation);text(details,'p','尚未确认：'+c.uncertainty);
    if(c.layer_hypothesis)text(details,'p','声音层假设：'+c.layer_hypothesis);
    for(const e of c.evidence) {
      const candidate=g=>(e.candidates[g]||[]).slice(0,2).map(r=>`${r.label} (${r.cosine_similarity.toFixed(3)})`).join(' / ');
      text(details,'p',`${e.engine} ${e.start.toFixed(0)}–${e.end.toFixed(0)} 秒 · 声音来源：${candidate('instruments')}；质感：${candidate('timbre')}；氛围：${candidate('mood')}。相似度不可跨模型比较。`);
    }
    if(c.separation.status==='completed') {
      const a=text(details,'a','单独听人声、鼓或伴奏');a.href=c.separation.player;
      a.onclick=()=>el('pause').click();
      text(details,'p','分轨是估计槽位，未人工核对纯度。请先比较原混音，检查串音或失真。');
      for(const s of c.separation.layers)text(details,'p',`${s.slot} 槽位：前窗 ${s.before_dbfs.toFixed(1)} → 后窗 ${s.after_dbfs.toFixed(1)} dBFS；不等同真实乐器响度。`);
    }
    const row=rows[index];
    const options={reaction:['未评价','喜欢','无感','不喜欢'],description_match:['未核对','符合','部分符合','不符合'],separation_quality:['未核对','可辅助辨听','明显串音或失真','无法判断']};
    const names={reaction:'个人感受',description_match:'描述是否符合听感',separation_quality:'分轨质量',layer:'你注意到的声音层',reason:'原因、联想或与前段的区别'};
    for(const f of fields.filter(f=>f!=='reaction')) {
      const label=text(f==='reason'||f==='layer'?optional:details,'label',names[f]+' ');label.style.cssText='display:block;margin:12px 0';
      let input;
      if(options[f]) {
        input=text(label,'select','');for(const option of options[f])text(input,'option',option);
        if(!options[f].includes(row[f]))row[f]=options[f][0];
      } else {input=text(label,'textarea','');input.rows=2;input.maxLength=2000;input.style.width='95%';}
      input.value=row[f];input.oninput=()=>{row[f]=input.value;changed();};
    }
  }
  el('previous-fragment').onclick=()=>{el('pause').click();active--;showCard();};
  el('next-fragment').onclick=()=>{el('pause').click();active++;showCard();};
  el('simple-playstatus').append(el('playstatus'));
  showCard();
  let exportURL;
  el('save-feedback').onclick=async()=>{
    const payload={schema_version:2,report_id:fragments.report_id,feedback:rows};
    const output=JSON.stringify(payload,null,2);el('feedback-json').hidden=false;el('feedback-json').value=output;
    if(exportURL)URL.revokeObjectURL(exportURL);
    exportURL=URL.createObjectURL(new Blob([output],{type:'application/json'}));
    const a=el('feedback-download');a.href=exportURL;a.download=t.slug+'-feedback.json';a.hidden=false;
    el('feedback-status').textContent='已整理反馈，可下载或复制 JSON。';
    if(location.protocol==='http:'&&location.hostname==='127.0.0.1') {
      el('save-feedback').disabled=true;
      try {
        const r=await fetch('/__fragment_feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:output});
        if(!r.ok)throw new Error('HTTP '+r.status);
        const saved=await r.json();a.href=saved.url;a.download=saved.file;
        el('feedback-status').textContent='已保存到本机 listening-exports/'+saved.file;
      } catch(e) {el('feedback-status').textContent='本机保存未完成：'+e.message+'。请下载或复制 JSON。';}
      finally {el('save-feedback').disabled=false;}
    }
  };
  window.addEventListener('pagehide',()=>{if(exportURL)URL.revokeObjectURL(exportURL);});
  if(!storageAvailable)el('feedback-status').textContent='浏览器草稿不可用，请导出保存。';
  compare();
})();
