/* Local-only media controller. Custom controls avoid the embedded browser's native media UI. */
(() => {
  const el = id => document.getElementById(id);
  const audio = el('audio'), track = el('track'), seek = el('seek');
  const offset = data.range.start, duration = data.range.end - offset;
  let position = 0, ready = false, wantPlay = false, stopAt = null, revision = 0;
  let exportURL = null;
  const marks = [];
  const clamp = t => Math.max(0, Math.min(duration, t));
  const status = message => { el('playstatus').textContent = message; };
  el('source').textContent = `${data.source.name} · 原文件 ${offset.toFixed(2)}–${data.range.end.toFixed(2)} 秒`;
  if (data.listening) el('source').textContent += ` · PCM16 试听，共同增益 ${data.listening.shared_gain_db.toFixed(2)} dB`;
  if (data.pitch_plot) { el('pitchplot').hidden = false; el('pitchimage').src = data.pitch_plot; }
  seek.min = offset; seek.max = data.range.end; seek.value = offset;
  function showPosition() {
    const t = position + offset;
    el('clock').textContent = `原文件位置 ${t.toFixed(2)} 秒`;
    seek.value = t;
    const chord = data.tonal.chords.find(c => t >= c.start && t < c.end);
    el('chord').textContent = '和弦候选：' + (chord?.candidate || '无');
  }
  function addTrack(name, path) {
    const option = document.createElement('option'); option.textContent = name; option.value = path; track.append(option);
  }
  addTrack('原混音', data.listening?.tracks.original.path || 'source.wav');
  for (const s of data.separation?.stems || []) addTrack(s.name + '（模型分离）', data.listening?.tracks[s.name]?.path || s.path);
  if (data.melody?.preview) addTrack('主旋律候选（合成正弦音）', data.melody.preview);
  function pause(message = '已暂停') {
    wantPlay = false; audio.pause();
    if (ready) position = clamp(audio.currentTime);
    showPosition(); status(message);
  }
  async function resume() {
    wantPlay = true;
    if (!ready) { status('正在加载，加载后播放'); return; }
    if (position >= duration - .01) { position = 0; stopAt = null; audio.currentTime = 0; }
    const token = revision;
    try {
      await audio.play();
      if (token !== revision) return;
      if (!wantPlay) { audio.pause(); return; }
      status('正在播放：' + track.selectedOptions[0].textContent);
    } catch (error) {
      if (token !== revision || !wantPlay || error.name === 'AbortError') return;
      wantPlay = false; status('播放失败：' + error.message + '。可重试播放或直接打开 WAV 文件。');
    }
  }
  function jump(absolute, end = null, playNow = true) {
    position = clamp(absolute - offset); stopAt = end === null ? null : clamp(end - offset);
    if (ready) audio.currentTime = position;
    showPosition(); if (playNow) resume();
  }
  function loadTrack() {
    if (ready) position = clamp(audio.currentTime);
    ready = false; const token = ++revision;
    audio.pause(); status('正在加载：' + track.selectedOptions[0].textContent);
    // Replace callbacks before src/load. A newer change invalidates pending play promises.
    audio.onloadedmetadata = () => {
      if (token !== revision) return;
      ready = true;
      position = clamp(position); audio.currentTime = Math.min(position, audio.duration);
      showPosition(); if (wantPlay) resume(); else status('已就绪：' + track.selectedOptions[0].textContent);
    };
    audio.onerror = () => {
      if (token !== revision) return;
      ready = false; wantPlay = false; status('音频加载失败（' + (audio.error?.code || '未知') + '），请检查本地服务和音轨文件。');
    };
    audio.src = track.value; audio.load();
  }
  track.onchange = loadTrack;
  el('resume').onclick = resume; el('pause').onclick = () => pause();
  el('restart').onclick = () => { pause(); jump(offset, null, false); };
  seek.oninput = () => jump(Number(seek.value), null, wantPlay);
  audio.ontimeupdate = () => {
    if (!ready) return;
    position = clamp(audio.currentTime);
    if (stopAt !== null && position >= stopAt) {
      const end = stopAt; stopAt = null; pause('片段播放结束');
      audio.currentTime = end; position = end;
    }
    showPosition();
  };
  audio.onended = () => { wantPlay = false; stopAt = null; position = duration; showPosition(); status('播放结束'); };
  function button(parent, label, a, b) {
    const button = document.createElement('button'); button.textContent = label; button.onclick = () => jump(a,b); parent.append(button);
  }
  for (const s of data.structure.segments) button(el('segments'), `${s.label} ${s.start.toFixed(1)}–${s.end.toFixed(1)}s`,s.start,s.end);
  for (const [i,r] of data.structure.repeat_candidates.entries()) {
    const row = document.createElement('div'); row.textContent = `${i+1}. 特征相似度 ${r.similarity.toFixed(3)} `;
    button(row,`A ${r.start_a.toFixed(1)}s`,r.start_a,r.end_a); button(row,`B ${r.start_b.toFixed(1)}s`,r.start_b,r.end_b); el('repeats').append(row);
  }
  function mark(label) {
    if (ready) position = clamp(audio.currentTime);
    const item = {time:position+offset,label,track:track.selectedOptions[0].textContent}; marks.push(item);
    const li = document.createElement('li'); li.textContent = `${item.time.toFixed(2)} 秒：${label} · ${item.track}`; el('marks').append(li);
  }
  el('like').onclick = () => mark('喜欢'); el('dislike').onclick = () => mark('不喜欢');
  el('export').onclick = async () => {
    const payload = {schema_version:1,source_sha256:data.source.sha256,range:data.range,marks:marks.map(m=>({...m}))};
    const text = JSON.stringify(payload,null,2);
    el('exportlabel').hidden = false; el('exportjson').value = text;
    if (exportURL) URL.revokeObjectURL(exportURL);
    exportURL = URL.createObjectURL(new Blob([text],{type:'application/json'}));
    const download = el('download'); download.href = exportURL; download.download = 'listening-marks.json'; download.hidden = false;
    status('标记已整理，请点击“下载标记 JSON”保存；也可复制导出内容。');
    if (location.protocol === 'http:' && location.hostname === '127.0.0.1') {
      el('export').disabled = true;
      try {
        const response = await fetch('/__listening_marks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
        if (!response.ok) throw new Error('HTTP '+response.status);
        const saved = await response.json();
        download.href = saved.url; download.download = saved.file;
        status('标记已保存到本机 results/listening-exports/'+saved.file+'；可通过下方链接下载副本。');
      } catch (error) {
        status('本机保存未完成：'+error.message+'。导出内容仍在下方，可复制保存。');
      } finally { el('export').disabled = false; }
    }
  };
  window.addEventListener('pagehide', () => { audio.pause(); if (exportURL) URL.revokeObjectURL(exportURL); });
  showPosition(); loadTrack();
})();
