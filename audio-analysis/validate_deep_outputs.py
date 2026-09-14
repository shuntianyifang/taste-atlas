"""Validate completed report contracts and optionally compare an earlier CLAP run."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
import soundfile as sf
from deep_analysis import ROOT,digest,write_json


def validate(out, baseline=None):
    out=Path(out).resolve();r=json.loads((out/'report.json').read_text(encoding='utf8'))
    assert r['completed'] and r['separation']['status']=='completed'
    assert r['melody']['status']=='candidate'
    assert digest(Path(r['source']['path']))==r['source']['sha256']
    assert digest(out/'source.wav')==r['decoded_sha256']
    start,end=r['range']['start'],r['range']['end']
    assert abs(end-start-r['range']['duration'])<1e-6
    assert [s['name'] for s in r['separation']['stems']]==['drums','bass','other','vocals']
    for s in r['separation']['stems']:
        assert digest(out/s['path'])==s['sha256']
        info=sf.info(out/s['path']);assert info.frames==s['samples'] and info.channels==2 and info.samplerate==44100
        assert abs(info.duration-(end-start))<=1/44100
        for b in sf.blocks(out/s['path'],blocksize=65536):assert np.isfinite(b).all()
    for name,track in r['listening']['tracks'].items():
        assert digest(out/track['path'])==track['sha256']
        assert sf.info(out/track['path']).subtype=='PCM_16'
    for name in ['melodia.csv','pitch.csv']:
        with (out/name).open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
        ts=[float(row['time']) for row in rows]
        assert all(start<=t<end for t in ts) and all(a<b for a,b in zip(ts,ts[1:]))
    for row in r['structure']['segments']:assert start<=row['start']<row['end']<=end
    assert all(start<=row['start']<row['end']<=end for row in r['tonal']['chords'])
    for file in ['report.md','player.html','overview.png','pitch-stems.png','stem-energy.csv','melodia-sine.wav']:
        assert (out/file).stat().st_size>0
    if baseline:
        old=json.loads(Path(baseline).read_text(encoding='utf8'));match=[t for t in old['tracks'] if t['source_sha256']==r['source']['sha256']]
        assert len(match)==1 and start==0 and abs(match[0]['semantic']['selected_seconds']-(end-start))<1e-5
    record={'result':str(out),'source_sha256':r['source']['sha256'],'range':r['range'],
            'prior_source_and_duration_match':bool(baseline),'four_stems_finite_aligned':True,
            'listening_hashes_verified':True,'timestamps_verified':True,'browser_playback_verified':None,
            'browser_verification_scope':'Not executed by this CLI; see PLAYER_ACCEPTANCE.md'}
    write_json(out/'verification.json',record);return record


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directories',nargs='+',type=Path);p.add_argument('--baseline',type=Path)
    args=p.parse_args();print(json.dumps([validate(out,args.baseline) for out in args.directories],indent=2))
