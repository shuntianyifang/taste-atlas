"""Verify completed artifacts and render existing pitch candidates, without re-separating."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
import librosa
import soundfile as sf
from deep_analysis import digest,write_csv,write_json,render_player
from deep_features import pitch_candidates


def finish(out):
    out=Path(out).resolve();p=out/'report.json';r=json.loads(p.read_text(encoding='utf-8'))
    if not r.get('completed') or r['separation']['status']!='completed':raise ValueError('Incomplete analysis or separation')
    if digest(Path(r['source']['path']))!=r['source']['sha256'] or digest(out/'source.wav')!=r['decoded_sha256']:raise ValueError('Changed source')
    curves=[('混音谐波中的主导音高',r['pitch']['rows'])];energy=[]
    for s in r['separation']['stems']:
        path=out/s['path']
        if digest(path)!=s['sha256']:raise ValueError('Changed stem')
        audio,sr=sf.read(path,dtype='float32',always_2d=True)
        if sr!=44100 or audio.shape!=(s['samples'],2) or not np.isfinite(audio).all():raise ValueError('Bad stem contract')
        if abs(s['end']-r['range']['end'])>1/44100:raise ValueError('Misaligned stem')
        for start in range(0,len(audio),sr*10):
            rms=float(np.sqrt(np.mean(audio[start:start+sr*10]**2)))
            energy.append({'stem':s['name'],'start':r['range']['start']+start/sr,
                           'end':r['range']['start']+min(len(audio),start+sr*10)/sr,'rms_dbfs':20*np.log10(max(rms,1e-12))})
        if 'pitch_csv' in s:
            if s['name']=='bass' and s.get('pitch_range_hz')!=[32.7,523.25]:
                mono=librosa.resample(audio.mean(axis=1),orig_sr=sr,target_sr=11025)
                rows=pitch_candidates(mono,11025,r['range']['start'],32.7,523.25)
                write_csv(out/s['pitch_csv'],rows);s['pitch_range_hz']=[32.7,523.25]
                s['pitch_voiced_frames']=sum(x['hz'] is not None for x in rows);s['pitch_total_frames']=len(rows)
            else:
                with (out/s['pitch_csv']).open(encoding='utf-8-sig',newline='') as f:
                    rows=[{k:(float(v) if v else None) for k,v in row.items()} for row in csv.DictReader(f)]
            curves.append((s['pitch_role'],rows))
    if r.get('melody',{}).get('status')=='candidate':
        with (out/r['melody']['csv']).open(encoding='utf-8-sig',newline='') as f:
            rows=[{k:(float(v) if v else None) for k,v in row.items()} for row in csv.DictReader(f)]
        curves.append(('MELODIA 主旋律候选',rows))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif']=['Microsoft YaHei','DejaVu Sans']
    fig,axes=plt.subplots(len(curves)+1,1,figsize=(12,3*(len(curves)+1)),constrained_layout=True)
    for ax,(name,rows) in zip(axes,curves):
        ax.plot([x['time'] for x in rows],[x['midi'] if x['midi'] is not None else np.nan for x in rows],'.',ms=1)
        ax.set(title=name+'（不是准确乐谱）',ylabel='MIDI 音高',xlim=(r['range']['start'],r['range']['end']))
    for name in ['drums','bass','other','vocals']:
        e=[x for x in energy if x['stem']==name];axes[-1].plot([(x['start']+x['end'])/2 for x in e],[x['rms_dbfs'] for x in e],label=name)
    axes[-1].legend();axes[-1].set(title='模型分离声部的能量变化',ylabel='RMS dBFS',xlabel='原文件时间 / 秒')
    fig.savefig(out/'pitch-stems.png',dpi=130);plt.close(fig)
    write_csv(out/'stem-energy.csv',energy)
    r['pitch_plot']='pitch-stems.png';r['artifact_verification']={'source_unchanged':True,'four_stems_finite_and_aligned':True}
    write_json(p,r);render_player(out,r)
    text=(out/'report.md').read_text(encoding='utf8')
    if 'pitch-stems.png' not in text:
        with (out/'report.md').open('a',encoding='utf8') as f:f.write('\n\n[查看音高候选与声部能量图](pitch-stems.png) · [声部能量 CSV](stem-energy.csv)\n')
    print(json.dumps({'file':r['source']['name'],'sha256':r['source']['sha256'],'range':r['range'],
        'segments':len(r['structure']['segments']),'repeats':len(r['structure']['repeat_candidates']),
        'loudness':r['loudness'],'separation_seconds':r['separation']['inference_seconds'],
        'keys':r['tonal']['global_key_candidates']},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('result_directory',type=Path);finish(p.parse_args().result_directory)
