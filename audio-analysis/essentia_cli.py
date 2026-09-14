"""Standalone Essentia ONNX analysis, with offline enforcement."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import socket
import time
import uuid
from unittest.mock import patch
from analyze import decode, metadata, ROOT


def run_files(files, output, start=0., duration=None):
    import numpy as np
    from essentia_engine import EssentiaEngine, SR
    from essentia_reporting import write_track
    output.parent.mkdir(parents=True, exist_ok=True)
    began = time.perf_counter()
    with patch.object(socket.socket, 'connect', side_effect=RuntimeError('Network forbidden during analysis')):
        engine = EssentiaEngine()
        result = {'engine': 'essentia', 'initialization_seconds': time.perf_counter() - began,
                  'network_connect_blocked': True, 'completed': False, 'tracks': [],
                  'label_sha256': hashlib.sha256(json.dumps(engine.labels, sort_keys=True).encode()).hexdigest()}
        for i, source in enumerate(files):
            source = source.resolve(strict=True)
            length = duration if duration is not None else metadata(source)['length'] - start
            if not np.isfinite(start) or start < 0 or not .25 <= length <= 600:
                raise ValueError('Use finite start >=0 and .25–600 seconds')
            print(f'essentia: {source.name}', flush=True)
            with source.open('rb') as f:
                sha = hashlib.file_digest(f, 'sha256').hexdigest()
            t = time.perf_counter()
            y, sr = decode(source, start, length, SR)
            semantic = engine.analyze(y, sr, start)
            track = {'file': source.name, 'source_sha256': sha, 'elapsed_seconds': time.perf_counter() - t,
                     'semantic': semantic, 'artifact_directory': f'essentia-track-{i + 1}'}
            write_track(track, output.parent / track['artifact_directory'])
            result['tracks'].append(track)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        assert engine.analyze(np.zeros(SR * 2), SR)['status'] == 'insufficient_signal'
        assert engine.analyze(np.ones(SR), SR)['status'] == 'insufficient_signal'
        reference = ROOT / 'selftest/reference/sorohanro_-_solo-trumpet-06.ogg'
        if reference.exists():
            y, sr = decode(reference, 0, 10, SR)
            a, b = engine.analyze(y, sr), engine.analyze(y, sr)
            assert a['overall'] == b['overall']
            ranking = sorted(a['overall']['instrument'], key=lambda k: -a['overall']['instrument'][k])
            result['reference_check'] = {'instrument_scores': a['overall']['instrument'],
                'trumpet_rank': ranking.index('trumpet') + 1, 'trumpet_top1_correct': ranking[0] == 'trumpet',
                'deterministic': True, 'silence_and_short_abstention': True}
        result['completed'] = True
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    parser.add_argument('--start', type=float, default=0)
    parser.add_argument('--duration', type=float, default=60)
    parser.add_argument('--whole-file', action='store_true')
    args = parser.parse_args()
    if args.whole_file and args.start != 0:
        parser.error('--whole-file requires --start 0')
    output = ROOT / 'results' / ('essentia-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    output.mkdir(parents=True)
    run_files([args.file], output / 'essentia.json', args.start, None if args.whole_file else args.duration)
    print(output / 'essentia-track-1/report.md')


if __name__ == '__main__':
    main()
