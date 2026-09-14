"""Offline structural, tonal and original-channel audio analysis."""
import argparse
import csv
import hashlib
import html
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time
import uuid

ROOT=Path(__file__).resolve().parent
os.environ.setdefault('NUMBA_CACHE_DIR',str(ROOT/'.cache/numba'))
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.cache/matplotlib'))
import numpy as np
import librosa
import soundfile as sf
import imageio_ffmpeg
from analyze import metadata
from deep_features import structure, tonal, stereo_metrics, pitch_candidates


def digest(path):
    with open(path,'rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def offline(*args,**kwargs):
    raise RuntimeError('Audio inference must remain offline')


def decode_native(source, start, duration, target):
    info=metadata(source)
    if info.get('channels') not in (1,2):
        raise ValueError('Only native mono/stereo supported; do not silently downmix surround')
    command=[imageio_ffmpeg.get_ffmpeg_exe(),'-nostdin','-hide_banner','-loglevel','error',
             '-ss',str(start),'-i',str(source),'-t',str(duration),'-vn','-c:a','pcm_f32le',str(target)]
    subprocess.run(command,check=True,capture_output=True,timeout=180)
    audio,sr=sf.read(target,dtype='float32',always_2d=True)
    if len(audio)<2*sr or not np.isfinite(audio).all():
        raise ValueError('Need at least 2 seconds of finite audio')
    return audio,sr


def loudness(path):
    # loudnorm analyzes its input at native channels; output is discarded, never applied to source.
    proc=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-nostdin','-hide_banner','-i',str(path),
                         '-af','loudnorm=I=-23:TP=-1:LRA=7:print_format=json','-f','null','-'],
                        capture_output=True,check=True,timeout=240)
    text=proc.stderr.decode('utf-8',errors='replace')
    matches=re.findall(r'\{\s*"input_i".*?\}',text,re.S)
    if not matches:
        raise ValueError('FFmpeg did not return loudness measurements')
    raw=json.loads(matches[-1]); out={}
    for key in ['input_i','input_tp','input_lra','input_thresh']:
        value=float(raw[key]); out[key]=value if np.isfinite(value) else None
    out['method']='FFmpeg loudnorm input measurements (EBU R128); no normalization applied'
    return out


def write_csv(path,rows):
    if not rows:
        Path(path).write_text('status\nno_candidates\n',encoding='utf-8'); return
    with open(path,'w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


def render(output,result,similarity):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif']=['Microsoft YaHei','DejaVu Sans']
    start=result['range']['start']; end=result['range']['end']
    fig,axes=plt.subplots(3,1,figsize=(12,11),constrained_layout=True)
    axes[0].imshow(similarity,origin='lower',extent=[start,end,start,end],vmin=-1,vmax=1,cmap='magma',aspect='auto')
    axes[0].set(title='和声音级／音色自相似（亮色仅表示特征相近）',ylabel='原文件时间 / 秒')
    st=result['structure']; axes[1].plot(st['times'],st['novelty'])
    for seg in st['segments'][1:]: axes[1].axvline(seg['start'],color='tomato',alpha=.6)
    axes[1].set(title='变化强度与候选边界（不等同主歌／副歌）',ylabel='局部对比')
    rows=result['stereo']; xs=[(r['start']+r['end'])/2 for r in rows]
    axes[2].plot(xs,[r['rms_dbfs'][0] if r['rms_dbfs'][0] is not None else np.nan for r in rows],label='左／单声道 RMS')
    if result['source']['channels']==2:
        axes[2].plot(xs,[r['rms_dbfs'][1] if r['rms_dbfs'][1] is not None else np.nan for r in rows],label='右 RMS')
    axes[2].set(title='原始声道能量',xlabel='原文件时间 / 秒',ylabel='dBFS'); axes[2].legend()
    fig.savefig(output/'overview.png',dpi=130); plt.close(fig)
    lines=['# 结构、声部、旋律与声场分析',f"\n文件：{result['source']['name']}",
           f"\n实际范围：{start:.3f}–{end:.3f} 秒；保留 {result['source']['sample_rate']} Hz / {result['source']['channels']} 声道。",
           '\n[打开本地试听时间轴](player.html) · [完整 JSON](report.json) · [概览](overview.png)',
           '\n## 结构候选','\n变化点由色度／音色局部对比产生；重复项为固定 8 秒特征相似候选，不证明旋律主题相同。',
           '\n|段落|起点|终点|','|---|---:|---:|']
    for r in st['segments']: lines.append(f"|{r['label']}|{r['start']:.2f}|{r['end']:.2f}|")
    lines+=['\n## 调性与旋律候选', '\n全段调性候选：'+', '.join(f"{r['label']} ({r['correlation']:.3f})" for r in result['tonal']['global_key_candidates']),
            '\n和弦仅覆盖 24 种大小三和弦；N 表示静音或候选不明确。全段调性不用于断言转调。',
            f"\n音高状态：{result['pitch']['status']}。pYIN 为单声部假设下的音高候选，不是确定主旋律或多声部乐谱。",
            '\n## 原始声道与响度',f"\nFFmpeg 输入测量：{json.dumps(result['loudness'],ensure_ascii=False)}",
            '\n左右相关性、侧／中能量比和响度是测量值，不是母带质量评分。静音的无定义值用 null 表示。',
            '\n## 限制','\n'+ '\n'.join('- '+x for x in result['limitations'])]
    (output/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    render_player(output,result)


def render_player(output,result):
    data=json.dumps(result,ensure_ascii=False,allow_nan=False).replace('<','\\u003c')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>本地音乐分析与试听</title><style>body{font:16px system-ui;max-width:1000px;margin:40px auto;padding:0 20px;background:#111922;color:#dde5ef}button,select{background:#26394b;color:inherit;border:1px solid #52708a;padding:9px;margin:4px;border-radius:5px}audio{width:100%}section{background:#1b2734;padding:18px;margin:20px 0;border-radius:10px}small,p{line-height:1.7;color:#bbcad8}img{width:100%}input{width:100%}.warn{color:#f2cc8f}</style>
<h1>音乐的结构与层次</h1><p id="source"></p><p class="warn">所有段落、乐器分轨、旋律和和弦均为分析候选；点击片段复听确认。音频留在本机。</p>
<section><label>试听声部 <select id="track"></select></label><audio id="audio" preload="metadata" hidden></audio><div><button id="resume">播放</button><button id="pause">暂停</button><button id="restart">回到开头</button></div><label>原文件位置（秒）<input id="seek" type="range" step="0.01"></label><p id="clock"></p><p id="playstatus" role="status"></p><p id="chord"></p></section>
<section><h2>变化段落</h2><div id="segments"></div></section><section><h2>相似片段 A / B 对照</h2><div id="repeats"></div></section>
<section><h2>你的标记</h2><p>标记当前时刻后导出 JSON 保存；刷新会清空未导出的标记。下载不可用时，可复制下方导出内容。</p><button id="like">喜欢这里</button><button id="dislike">不喜欢这里</button><button id="export">导出标记</button><ul id="marks"></ul><label id="exportlabel" hidden>导出内容<textarea id="exportjson" readonly rows="12" style="width:100%"></textarea></label><a id="download" hidden>下载标记 JSON</a></section>
<section><img src="overview.png" alt="自相似、结构变化和原始声道能量图"></section>
<section id="pitchplot" hidden><h2>音高候选与声部变化</h2><img id="pitchimage" alt="音高候选与声部能量图"></section>
<script>const data=DATA;</script>'''
    script=(ROOT/'player_controls.js').read_text(encoding='utf-8')
    (output/'player.html').write_text(page.replace('DATA',data)+'<script>'+script+'</script></html>',encoding='utf-8')


def run(source, start=0, duration=60, whole=False, pitch=False, output=None):
    source=Path(source).resolve(); info=metadata(source)
    if not np.isfinite(start) or start<0 or not np.isfinite(duration) or duration<=0 or duration>600:
        raise ValueError('Use finite start >=0 and duration >0 <=600')
    if whole:
        if start!=0: raise ValueError('--whole-file cannot be combined with nonzero start')
        duration=float(info['length'])
        if duration>600: raise ValueError('Whole file exceeds 600 seconds; select a range')
    out=Path(output) if output else ROOT/'results'/('deep-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    out.mkdir(parents=True,exist_ok=False)
    started=time.perf_counter(); fingerprint=digest(source)
    audio,sr=decode_native(source,start,duration,out/'source.wav'); actual=len(audio)/sr
    print('Decoded native channels; measuring structure and tonal candidates...',flush=True)
    y=librosa.resample(audio.mean(axis=1),orig_sr=sr,target_sr=22050)
    hop=512; spec=librosa.stft(y,n_fft=2048,hop_length=hop)
    harmonic,_=librosa.decompose.hpss(spec)
    chroma=librosa.feature.chroma_stft(S=np.abs(harmonic)**2,sr=22050,n_fft=2048,hop_length=hop,tuning=0)
    mfcc=librosa.feature.mfcc(S=librosa.power_to_db(librosa.feature.melspectrogram(S=np.abs(spec)**2,sr=22050)),n_mfcc=14)
    times=librosa.frames_to_time(np.arange(chroma.shape[1]),sr=22050,hop_length=hop)
    rms=librosa.feature.rms(S=np.abs(spec),frame_length=2048,hop_length=hop)[0]
    st,sim=structure(chroma,mfcc,times,actual,start)
    if np.max(np.abs(audio))<10**(-65/20):
        st['segments']=[];st['repeat_candidates']=[];st['status']='abstained_silence'
    else: st['status']='candidates'
    result={'schema_version':1,'completed':False,'decoded_sha256':digest(out/'source.wav'),'source':{'name':source.name,'path':str(source),'sha256':fingerprint,'sample_rate':sr,'channels':audio.shape[1]},
            'range':{'start':start,'end':start+actual,'duration':actual},'structure':st,
            'tonal':tonal(chroma,times,rms,actual,start),'stereo':stereo_metrics(audio,sr,start),
            'loudness':loudness(out/'source.wav'),'pitch':{'status':'not_requested','rows':[]},
            'separation':{'status':'not_run','stems':[]},
            'limitations':['变化边界及重复候选未经人工标注验收，不等同曲式、主题或高潮真值。',
                           '大小三和弦与调性模板不能覆盖复杂和声；排名和相关性不是准确率。',
                           'pYIN 主导音高候选可能跟随低音或泛音；不会自动还原准确主旋律或乐谱。',
                           '源分离的 vocals/other 标签不证明原曲有人声；需要复听排查串音。']}
    if pitch:
        print('Estimating dominant pitch (single-voice assumption)...',flush=True)
        yy=librosa.resample(librosa.istft(harmonic,hop_length=hop,length=len(y)),orig_sr=22050,target_sr=11025)
        result['pitch']={'status':'candidate_on_harmonic_mix','sample_rate':11025,'rows':pitch_candidates(yy,11025,start)}
    if digest(source)!=fingerprint: raise ValueError('Source changed during analysis')
    write_csv(out/'segments.csv',st['segments']); write_csv(out/'repeats.csv',st['repeat_candidates'])
    write_csv(out/'chords.csv',result['tonal']['chords']); write_csv(out/'pitch.csv',result['pitch']['rows']); write_csv(out/'stereo.csv',result['stereo'])
    result['elapsed_seconds']=time.perf_counter()-started
    render(out,result,sim)
    np.save(out/'similarity.npy',sim,allow_pickle=False)
    result['completed']=True; write_json(out/'report.json',result)
    render_player(out,result)
    print(str(out),flush=True)
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source');parser.add_argument('--start',type=float,default=0)
    parser.add_argument('--duration',type=float,default=60);parser.add_argument('--whole-file',action='store_true');parser.add_argument('--pitch',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();socket.socket.connect=offline;socket.create_connection=offline
    run(args.source,args.start,args.duration,args.whole_file,args.pitch,args.output)
