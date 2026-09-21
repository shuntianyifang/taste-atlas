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


def tracking_diagnostics(pitch, hop_seconds=128/44100):
    """Describe failure risks, never estimate accuracy from output density."""
    pitch=np.asarray(pitch,dtype=float)
    if pitch.ndim!=1 or len(pitch)==0 or not np.isfinite(pitch).all() or (pitch<0).any():
        raise ValueError('Invalid pitch contour')
    active=pitch>0
    gaps=[];start=None
    for i,voiced in enumerate(np.r_[active,True]):
        if not voiced and start is None:start=i
        if voiced and start is not None:gaps.append((i-start)*hop_seconds);start=None
    adjacent=active[:-1]&active[1:]
    jumps=np.abs(12*np.log2(pitch[1:][adjacent]/pitch[:-1][adjacent]))
    return {'candidate_fraction':float(active.mean()),'longest_missing_seconds':max(gaps,default=0.),
            'missing_runs_over_one_second':sum(g>=1 for g in gaps),
            'adjacent_candidate_pairs':int(adjacent.sum()),
            'jumps_over_seven_semitones':int((jumps>7).sum()),
            'interpretation':'Coverage and jumps are diagnostic signals, not melody accuracy; missing output does not prove musical silence.'}


def compare_contours(a,b):
    a=np.asarray(a,dtype=float);b=np.asarray(b,dtype=float)
    if a.shape!=b.shape:raise ValueError('Contours must use identical frame times')
    da=tracking_diagnostics(a);db=tracking_diagnostics(b)
    both=(a>0)&(b>0);delta=np.abs(12*np.log2(a[both]/b[both]))
    return {'mix':da,'other':db,'joint_candidate_frames':int(both.sum()),
            'same_pitch_within_half_semitone_fraction':float(np.mean(delta<=.5)) if len(delta) else None,
            'near_octave_disagreement_fraction':float(np.mean(np.abs(delta-12)<=.5)) if len(delta) else None,
            'interpretation':'Agreement is consistency, not accuracy. Neither contour is ground truth.'}


def compare_other(out):
    """Keep the mix baseline and run identical MELODIA settings on a verified stem."""
    out=Path(out).resolve();r=json.loads((out/'report.json').read_text(encoding='utf8'))
    if not r.get('completed') or r.get('separation',{}).get('status')!='completed':raise ValueError('Completed separation required')
    if digest(r['source']['path'])!=r['source']['sha256'] or digest(out/'source.wav')!=r['decoded_sha256']:raise ValueError('Source changed')
    stem=next(s for s in r['separation']['stems'] if s['name']=='other')
    source=out/stem['path']
    if digest(source)!=stem['sha256']:raise ValueError('Stem changed')
    info=sf.info(source)
    if abs(info.duration-r['range']['duration'])>1/info.samplerate or abs(stem['start']-r['range']['start'])>1e-6:raise ValueError('Stem range differs')
    # Rerun both with the same code/settings rather than trusting an unbound cached contour.
    raw=[]
    for label,path in [('mix',out/'source.wav'),('other',source)]:
        y,sr=decode(path,0,r['range']['duration'],44100)
        pcm=out/f'melody-check-{label}.f32';target=out/f'melody-check-{label}.json'
        y.astype('<f4').tofile(pcm)
        subprocess.run(['node',str(ROOT/'melodia.cjs'),str(pcm),str(target)],check=True,timeout=600)
        native=json.loads(target.read_text(encoding='utf8'))
        n=min(len(native['pitch']),int(np.ceil(len(y)/128)))
        pitch=np.asarray(native['pitch'][:n]);confidence=np.asarray(native['confidence'][:n])
        if len(confidence)!=len(pitch) or not np.isfinite(confidence).all():raise ValueError('Invalid confidence')
        tracking_diagnostics(pitch)
        rows=[{'time':r['range']['start']+i*128/44100,'hz':float(f) if f>0 else None,
               'native_pitch_confidence':float(confidence[i])} for i,f in enumerate(pitch)]
        write_csv(out/f'melody-check-{label}.csv',rows)
        per_sample=np.repeat(pitch,128)[:len(y)];per_sample=np.pad(per_sample,(0,max(0,len(y)-len(per_sample))))
        sine=.08*np.sin(np.cumsum(per_sample)*2*np.pi/44100)*(per_sample>0)
        sf.write(out/f'melody-check-{label}-sine.wav',sine,44100,subtype='PCM_16')
        raw.append(pitch)
    comparison=compare_contours(*raw)
    comparison.update(status='candidate_comparison',source_sha256=r['source']['sha256'],decoded_sha256=r['decoded_sha256'],
        stem_sha256=stem['sha256'],range=r['range'],settings='MELODIA defaults, equal loudness, 44100 Hz, hop 128; voicing unchanged',
        preview='melody-check-other-sine.wav',baseline_preview='melody-check-mix-sine.wav',
        human_verified=False,automatic_winner=None,
        limitations=['other 槽位仍是多声部，可能串音、失真或遗漏真正的主旋律。','不以更多音高点作为替换原混音轮廓的理由。'])
    windows=[]
    for a in range(0,len(raw[0]),round(10*44100/128)):
        b=min(len(raw[0]),a+round(10*44100/128))
        windows.append(dict(start=r['range']['start']+a*128/44100,end=min(r['range']['end'],r['range']['start']+b*128/44100),
                            comparison=compare_contours(raw[0][a:b],raw[1][a:b])))
    comparison['windows']=windows
    if digest(r['source']['path'])!=r['source']['sha256'] or digest(source)!=stem['sha256']:raise ValueError('Source changed during comparison')
    write_json(out/'melody-comparison.json',comparison)
    r.setdefault('melody',{})['comparison']=comparison
    r['melody']['tracking_diagnostics']=comparison['mix']
    write_json(out/'report.json',r);render_player(out,r)
    lines=['# 旋律跟踪诊断','', '保持默认参数，将原混音与已校验的 other 分轨分别分析。原混音结果保留，不自动选择胜者。','',
           '| 输入 | 有候选时间占比 | 最长漏检（秒） | 相邻帧大跳次数 |','|---|---:|---:|---:|']
    for label in ('mix','other'):
        d=comparison[label];lines.append(f'| {label} | {d["candidate_fraction"]:.1%} | {d["longest_missing_seconds"]:.2f} | {d["jumps_over_seven_semitones"]} |')
    lines+=['','覆盖率不是准确率。大跳可能是真实音符、八度误差或跨声部错跟；不能单凭统计确定。',
            f'双方都有候选的帧数：{comparison["joint_candidate_frames"]}。其中半音以内一致比例：{comparison["same_pitch_within_half_semitone_fraction"]}。',
            '', '两个正弦试听轨仅用于人工核对音高走势，不是原曲分离出的乐器。未完成真实旋律标注及浏览器试听验收。',
            '', '[逐窗诊断与来源](melody-comparison.json) · [原混音轮廓](melody-check-mix.csv) · [分轨轮廓](melody-check-other.csv)']
    (out/'melody-comparison.md').write_text('\n'.join(lines),encoding='utf8')
    print(json.dumps({k:v for k,v in comparison.items() if k!='windows'},ensure_ascii=False))


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
                  tracking_diagnostics=tracking_diagnostics(pitch),
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
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('result_directory',type=Path);p.add_argument('--compare-other',action='store_true')
    args=p.parse_args()
    if args.compare_other:compare_other(args.result_directory)
    else:analyze(args.result_directory)
