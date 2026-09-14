"""MELODIA predominant-melody candidate, CSV and synthetic listening reference."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import numpy as np
import soundfile as sf
from deep_analysis import ROOT,digest,write_json,write_csv,render_player
from analyze import decode


def analyze(out):
    out=Path(out).resolve();p=out/'report.json';r=json.loads(p.read_text(encoding='utf-8'))
    if not r.get('completed') or digest(out/'source.wav')!=r['decoded_sha256']:raise ValueError('Incomplete or changed input')
    y,sr=decode(out/'source.wav',0,r['range']['duration'],44100)
    pcm=out/'melodia-input.f32';y.astype('<f4').tofile(pcm)
    raw=out/'melodia-raw.json'
    subprocess.run(['node',str(ROOT/'melodia.cjs'),str(pcm),str(raw)],check=True,timeout=600)
    result=json.loads(raw.read_text(encoding='utf-8'));pitch=np.asarray(result.pop('pitch'));scores=np.asarray(result.pop('confidence'))
    times=np.arange(len(pitch))*128/44100;keep=times<len(y)/sr
    times=times[keep];pitch=pitch[keep];scores=scores[keep]
    if len(pitch)==0 or not np.isfinite(pitch).all() or not np.isfinite(scores).all():raise ValueError('Invalid output')
    rows=[{'time':r['range']['start']+float(t),'hz':float(f) if f>0 else None,
           'midi':float(69+12*np.log2(f/440)) if f>0 else None,'native_pitch_confidence':float(c)} for t,f,c in zip(times,pitch,scores)]
    write_csv(out/'melodia.csv',rows)
    # Sonify the predicted contour for manual comparison, explicitly not separated music.
    per_sample=np.repeat(np.maximum(pitch,0),128)[:len(y)]
    per_sample=np.pad(per_sample,(0,max(0,len(y)-len(per_sample))))
    phase=np.cumsum(per_sample.astype(np.float64))*2*np.pi/sr
    sine=(.08*np.sin(phase)*(per_sample>0)).astype(np.float32)
    sf.write(out/'melodia-sine.wav',sine,sr,subtype='PCM_16')
    result.update(status='abstained_silence' if result.get('abstention') else 'candidate',csv='melodia.csv',preview='melodia-sine.wav',frames=len(rows),
                  voiced_frames=int(np.sum(pitch>0)),voiced_fraction=float(np.mean(pitch>0)),
                  start=r['range']['start'],end=r['range']['end'],
                  limitations=['MELODIA 主导旋律轮廓仍可能跟随伴奏或发生八度错误。',
                               '原生 pitchConfidence 不作校准概率；不调整默认 voicingTolerance 掩盖漏检。',
                               '合成正弦音只是音高候选的听觉展示，不是从原曲分离出的真实乐器。'])
    r['melody']=result;write_json(p,r);render_player(out,r)
    text=(out/'report.md').read_text(encoding='utf8')
    if 'melodia.csv' not in text:
        with (out/'report.md').open('a',encoding='utf8') as f:
            f.write('\n\n## MELODIA 主旋律候选\n\n[时间轴 CSV](melodia.csv) · [音高合成正弦音](melodia-sine.wav)。默认参数、等响度滤波、44.1 kHz、128 点步进。不是准确乐谱或真实分离乐器。\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('result_directory',type=Path);analyze(p.parse_args().result_directory)
