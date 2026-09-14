"""Create browser PCM16 listening copies with one shared attenuation, never modify analysis audio."""
import argparse
import json
from pathlib import Path
import numpy as np
import soundfile as sf
from deep_analysis import digest, write_json, render_player


def prepare(out):
    out=Path(out).resolve();p=out/'report.json';r=json.loads(p.read_text(encoding='utf-8'))
    if not r.get('completed'):raise ValueError('Incomplete analysis')
    inputs=[('original',out/'source.wav',r['decoded_sha256'])]
    for stem in r['separation'].get('stems',[]):inputs.append((stem['name'],out/stem['path'],stem['sha256']))
    peak=0.
    for _,path,sha in inputs:
        if digest(path)!=sha:raise ValueError('Audio changed')
        for block in sf.blocks(path,blocksize=65536,dtype='float32',always_2d=True):
            if not np.isfinite(block).all():raise ValueError('Non-finite audio')
            peak=max(peak,float(np.max(np.abs(block))))
    gain=min(1.,.999/max(peak,1e-12));folder=out/'listening';folder.mkdir(exist_ok=True)
    paths={}
    for name,path,sha in inputs:
        target=folder/(name+'.wav');info=sf.info(path)
        with sf.SoundFile(target,'w',samplerate=info.samplerate,channels=info.channels,subtype='PCM_16') as f:
            for block in sf.blocks(path,blocksize=65536,dtype='float32',always_2d=True):f.write(block*gain)
        paths[name]={'path':target.relative_to(out).as_posix(),'sha256':digest(target)}
    r['listening']={'format':'WAV PCM16','shared_gain_db':float(20*np.log10(gain)), 'tracks':paths,
                    'note':'所有试听轨使用相同衰减防止削波；原始浮点音频及分析数值不变。'}
    write_json(p,r);render_player(out,r);print(str(out/'player.html'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('result_directory',type=Path);prepare(p.parse_args().result_directory)
