"""Auditable DSP candidates. None of these scores are calibrated probabilities."""
import numpy as np
import librosa
from scipy.signal import find_peaks

NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def unit(x):
    return x / np.maximum(np.linalg.norm(x, axis=0, keepdims=True), 1e-10)


def structure(chroma, mfcc, times, duration, offset=0):
    """0.5s bins; local contrast over 4s and aligned 8s repetition candidates."""
    step = .5
    edges = np.arange(0, duration, step)
    c, m = [], []
    for left in edges:
        idx = (times >= left) & (times < min(duration, left + step))
        c.append(chroma[:, idx].mean(axis=1) if idx.any() else np.zeros(12))
        m.append(mfcc[1:, idx].mean(axis=1) if idx.any() else np.zeros(mfcc.shape[0]-1))
    c = unit(np.asarray(c).T)
    m = np.asarray(m).T
    m = unit((m - m.mean(axis=1, keepdims=True)) / np.maximum(m.std(axis=1, keepdims=True), 1))
    x = np.concatenate([np.sqrt(.7)*c, np.sqrt(.3)*m])
    sim = np.clip(x.T @ x, -1, 1)
    novelty = np.zeros(len(edges))
    radius = 8
    for k in range(radius, len(edges)-radius):
        a, b = unit(x[:, k-radius:k].mean(axis=1, keepdims=True)), unit(x[:, k:k+radius].mean(axis=1, keepdims=True))
        novelty[k] = max(0, 1-float((a.T @ b).item()))
    peaks, _ = find_peaks(novelty, distance=16, prominence=.08)
    peaks = [int(i) for i in peaks if novelty[i] >= .12 and edges[i] >= 8 and duration-edges[i] >= 8]
    cuts = [0.] + [float(edges[i]) for i in peaks] + [duration]
    segments = [{'start': offset+a, 'end': offset+b, 'label': f'段落 {i+1}'} for i, (a,b) in enumerate(zip(cuts, cuts[1:]))]
    candidates = []
    width = 16
    for a in range(0, len(edges)-width+1, 4):
        for b in range(a+width+8, len(edges)-width+1, 4):
            score = float(np.mean(np.sum(x[:, a:a+width] * x[:, b:b+width], axis=0)))
            if score >= .80:
                candidates.append((score,a,b))
    repeats = []
    for score,a,b in sorted(candidates, reverse=True):
        if any(abs(offset+edges[a]-r['start_a']) < 8 and abs(offset+edges[b]-r['start_b']) < 8 for r in repeats):
            continue
        repeats.append({'start_a': offset+float(edges[a]), 'end_a': offset+min(duration,float(edges[a])+8),
                        'start_b': offset+float(edges[b]), 'end_b': offset+min(duration,float(edges[b])+8), 'similarity': score})
        if len(repeats) == 12:
            break
    return {'method': 'chroma70_mfcc30_local_contrast_v1', 'bin_seconds': step,
            'boundary_min_spacing_seconds': 8, 'repeat_window_seconds': 8,
            'repeat_min_similarity': .80, 'segments': segments, 'repeat_candidates': repeats,
            'times': (edges+offset).tolist(), 'novelty': novelty.tolist()}, sim


def tonal(chroma, times, rms, duration, offset=0):
    templates, names = [], []
    for mode, third in [('maj',4), ('min',3)]:
        for root in range(12):
            t = np.zeros(12); t[[root,(root+third)%12,(root+7)%12]] = 1
            templates.append(t/np.linalg.norm(t)); names.append(NAMES[root]+':'+mode)
    templates = np.asarray(templates)
    windows = []
    for a in np.arange(0,duration,2.):
        idx = (times>=a)&(times<min(a+2,duration))
        vector = chroma[:,idx].mean(axis=1) if idx.any() else np.zeros(12)
        scores = templates @ unit(vector[:,None])[:,0]
        order = np.argsort(scores)[::-1][:3]
        active = bool(idx.any() and np.max(rms[idx]) > 10**(-65/20))
        margin = float(scores[order[0]]-scores[order[1]])
        label = names[order[0]] if active and scores[order[0]] >= .65 and margin >= .04 else 'N/不确定'
        windows.append({'start': offset+float(a), 'end': offset+min(float(a)+2,duration), 'candidate':label,
                        'margin':margin, 'top3':[{'label':names[i],'similarity':float(scores[i])} for i in order] if active else []})
    profiles = {'major':[6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88],
                'minor':[6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17]}
    v = chroma.mean(axis=1); keys=[]
    if np.std(v)>1e-8 and np.max(rms)>10**(-65/20):
        for mode,p in profiles.items():
            for root in range(12):
                keys.append({'label':NAMES[root]+' '+mode,'correlation':float(np.corrcoef(v,np.roll(p,root))[0,1])})
    return {'method':'24_triad_cosine_2s_and_Krumhansl_Kessler_profiles',
            'chords':windows,'global_key_candidates':sorted(keys,key=lambda r:r['correlation'],reverse=True)[:3],
            'limitations':['仅大小三和弦候选；不支持七和弦、转位和精确转调判断。',
                           '0.65 相似度及 0.04 排名差为固定启发式拒判阈值，不是置信度。']}


def stereo_metrics(audio, sr, offset=0):
    if audio.ndim != 2 or audio.shape[1] not in (1,2) or not np.isfinite(audio).all():
        raise ValueError('Expected finite mono or stereo samples')
    rows=[]
    for begin in range(0,len(audio),sr*10):
        block=audio[begin:begin+sr*10].astype(np.float64)
        def db(v):
            return float(20*np.log10(v)) if v>1e-12 else None
        rms=np.sqrt(np.mean(block**2,axis=0)); peak=np.max(np.abs(block),axis=0)
        row={'start':offset+begin/sr,'end':offset+(begin+len(block))/sr,
             'rms_dbfs':[db(v) for v in rms], 'sample_peak_dbfs':[db(v) for v in peak],
             'lr_correlation':None,'side_to_mid_db':None,'right_minus_left_db':None}
        if block.shape[1]==2:
            l,r=block.T
            if np.std(l)>1e-10 and np.std(r)>1e-10:
                row['lr_correlation']=float(np.corrcoef(l,r)[0,1])
            mid=np.sqrt(np.mean(((l+r)/2)**2)); side=np.sqrt(np.mean(((l-r)/2)**2))
            row['side_to_mid_db']=db(side/mid) if mid>1e-12 else None
            row['right_minus_left_db']=db(rms[1]/rms[0]) if rms[0]>1e-12 else None
        rows.append(row)
    return rows


def pitch_candidates(y, sr, offset=0, fmin=65.4, fmax=1046.5):
    """pYIN chunking bounds memory; dominant monophonic estimate, NOT a score."""
    rows=[]
    for begin in range(0,len(y),sr*20):
        left=max(0,begin-sr); right=min(len(y),begin+sr*21)
        block=y[left:right]
        if len(block)<2048 or np.max(np.abs(block))<10**(-65/20):
            continue
        f0, voiced, prob=librosa.pyin(block, sr=sr, fmin=fmin, fmax=fmax, frame_length=2048, hop_length=256)
        ts=librosa.times_like(f0,sr=sr,hop_length=256)+left/sr
        for t,hz,v,p in zip(ts,f0,voiced,prob):
            if begin/sr<=t<min(len(y)/sr,begin/sr+20):
                ok=bool(v and np.isfinite(hz) and p>=.5)
                rows.append({'time':offset+float(t),'hz':float(hz) if ok else None,
                             'midi':float(librosa.hz_to_midi(hz)) if ok else None,
                             'voicing_probability':float(p) if np.isfinite(p) else None})
    return rows
