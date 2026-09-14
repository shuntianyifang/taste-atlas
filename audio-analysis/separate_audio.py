"""Offline HTDemucs adapter for a completed deep_analysis result directory."""
import argparse
import json
from pathlib import Path
import socket
import time
from importlib.metadata import version

from deep_analysis import ROOT, digest, offline, write_json, write_csv, render_player
from deep_features import pitch_candidates
from setup_separation import SHA256
import numpy as np
import librosa
import soundfile as sf


def verify_model(directory=None):
    directory=Path(directory or ROOT/'models/demucs')
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    if manifest['file']!='955717e8-8726e21a.th' or manifest['demucs_version']!='4.0.1':
        raise ValueError('Unexpected model or version')
    path=directory/manifest['file']
    if path.stat().st_size!=manifest['bytes'] or digest(path)!=manifest['sha256'] or manifest['sha256']!=SHA256:
        raise ValueError('Model checksum mismatch')
    return path,manifest


def verify_input(out):
    out=Path(out).resolve()
    result=json.loads((out/'report.json').read_text(encoding='utf-8'))
    if not result.get('completed'):raise ValueError('Analysis not complete')
    if result.get('separation',{}).get('status')=='completed':raise ValueError('Separation already completed; create a new result to rerun')
    r=result['range']
    if not all(np.isfinite(r[k]) for k in ['start','end','duration']) or r['start']<0 or not 2<=r['duration']<=600 or abs(r['end']-r['start']-r['duration'])>1e-6:
        raise ValueError('Invalid or excessive analysis range')
    source=Path(result['source']['path'])
    if digest(source)!=result['source']['sha256']:raise ValueError('Original audio fingerprint mismatch')
    audio,sr=sf.read(out/'source.wav',dtype='float32',always_2d=True)
    if sr!=result['source']['sample_rate'] or audio.shape[1]!=result['source']['channels'] or abs(len(audio)/sr-result['range']['duration'])>1/sr:
        raise ValueError('Selected audio range or format mismatch')
    if not np.isfinite(audio).all():raise ValueError('Non-finite samples')
    native_hash=digest(out/'source.wav')
    if native_hash!=result.get('decoded_sha256'):raise ValueError('Decoded audio fingerprint missing or mismatched; rerun deep_analysis')
    return result,audio,sr,native_hash


def separate(out, stem_pitch=False):
    import torch
    from demucs.states import load_model
    from demucs.apply import apply_model
    if version('demucs')!='4.0.1':raise ValueError('Use locked Demucs 4.0.1 environment')
    out=Path(out).resolve();report_path=out/'report.json'
    result,audio,sr,native_hash=verify_input(out)
    source=Path(result['source']['path'])
    path,manifest=verify_model();socket.socket.connect=offline;socket.create_connection=offline
    torch.set_num_threads(4);torch.manual_seed(0)
    started=time.perf_counter()
    # This legacy official checkpoint contains its model class, not just tensors.
    # Only the fixed official asset above, verified before deserialization, is accepted.
    package=torch.load(path,map_location='cpu',weights_only=False)
    model=load_model(package,strict=True).eval()
    if list(model.sources)!=['drums','bass','other','vocals'] or model.samplerate!=44100:raise ValueError('Unexpected model contract')
    init_seconds=time.perf_counter()-started
    wav=librosa.resample(audio.T,orig_sr=sr,target_sr=44100,axis=-1)
    if wav.shape[0]==1:wav=np.repeat(wav,2,axis=0)
    tensor=torch.from_numpy(wav.copy());ref=tensor.mean(0);mean=ref.mean();std=ref.std()
    if std<1e-8:
        result['separation']={'status':'abstained_silence_or_mono_cancellation','stems':[]};write_json(report_path,result);render_player(out,result);return
    result['separation']={'status':'running','stems':[]};write_json(report_path,result)
    print('Separating drums / bass / other / vocals, CPU FP32, offline...',flush=True)
    inference=time.perf_counter()
    with torch.inference_mode():
        estimate=apply_model(model,((tensor-mean)/std)[None],device='cpu',shifts=0,split=True,
                             overlap=.25,segment=7.8,progress=True,num_workers=0)[0]
    estimate=estimate*std+mean
    if estimate.shape!=(4,2,wav.shape[1]) or not torch.isfinite(estimate).all():raise ValueError('Invalid model output')
    inference_seconds=time.perf_counter()-inference
    stemdir=out/('stems-'+time.strftime('%Y%m%d-%H%M%S'));stemdir.mkdir(exist_ok=False)
    stems=[]
    for name,samples in zip(model.sources,estimate.numpy()):
        p=stemdir/(name+'.wav');sf.write(p,samples.T,44100,subtype='FLOAT')
        stem={'name':name,'path':p.relative_to(out).as_posix(),'sha256':digest(p),'sample_rate':44100,
              'samples':samples.shape[1],'start':result['range']['start'],
              'end':result['range']['start']+samples.shape[1]/44100,
              'rms_dbfs':float(20*np.log10(max(float(np.sqrt(np.mean(samples**2))),1e-12)))}
        if stem_pitch and name in ('other','bass'):
            print(f'Estimating {name} pitch candidates...',flush=True)
            mono=librosa.resample(samples.mean(axis=0),orig_sr=44100,target_sr=11025)
            bounds=(32.7,523.25) if name=='bass' else (65.4,1046.5)
            rows=pitch_candidates(mono,11025,result['range']['start'],*bounds)
            csvpath=stemdir/(name+'-pitch.csv');write_csv(csvpath,rows)
            stem['pitch_csv']=csvpath.relative_to(out).as_posix()
            stem['pitch_voiced_frames']=sum(r['hz'] is not None for r in rows)
            stem['pitch_total_frames']=len(rows)
            stem['pitch_range_hz']=list(bounds)
            stem['pitch_role']='低音音高候选' if name=='bass' else '其他伴奏中的主导音高候选；不保证主旋律'
        stems.append(stem)
    if digest(source)!=result['source']['sha256'] or digest(out/'source.wav')!=native_hash:raise ValueError('Audio changed during separation')
    residual=estimate.sum(0).numpy()-wav
    result['separation']={'status':'completed','model':manifest,'offline':True,'device':'cpu','shifts':0,'overlap':.25,'segment':7.8,
                          'init_seconds':init_seconds,'inference_seconds':inference_seconds,'stems':stems,
                          'reconstruction_residual_rms':float(np.sqrt(np.mean(residual**2))),
                          'limitations':['声部名称是模型输出槽位，不证明真实乐器存在。','四轨分离可能串音和失真；未取得原始分轨，不报告分离准确率。',
                                         '残差仅检查混音重构差异，不能证明声部纯度。','other 音高仍可能跟踪和声或泛音。']}
    write_json(report_path,result);render_player(out,result)
    with (out/'report.md').open('a',encoding='utf-8') as f:
        f.write('\n\n## 四声部分离\n\nHTDemucs 4.0.1，本机 CPU 离线推理完成。可在试听页切换原混音、drums、bass、other、vocals。各轨为模型估计，不能据 vocals 轨直接断言原曲有人声。\n')
        for s in stems:f.write(f"\n- [{s['name']}]({s['path']})"+(f" · [音高候选 CSV]({s['pitch_csv']})" if 'pitch_csv' in s else ''))
    print(str(out/'player.html'),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('result_directory',type=Path);p.add_argument('--stem-pitch',action='store_true')
    args=p.parse_args();separate(args.result_directory,args.stem_pitch)
