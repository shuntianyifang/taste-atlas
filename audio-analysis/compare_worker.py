"""Run one model offline on an explicit list of local recordings."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import time
from unittest.mock import patch

from analyze import decode, metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', choices=['clap', 'muq', 'essentia'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('files', nargs='+', type=Path)
    args = parser.parse_args()
    if args.engine == 'essentia':
        from essentia_cli import run_files
        run_files(args.files, args.output)
        print(args.output, flush=True)
        return
    start = time.perf_counter()
    # Enforce offline operation for imports, model loading, tokenization and inference.
    with patch.object(socket.socket, 'connect', side_effect=RuntimeError('Network forbidden during analysis')):
        if args.engine == 'clap':
            from semantic import ClapEngine
            engine, sr = ClapEngine(), 48000
        else:
            from muq_semantic import MuQEngine
            engine, sr = MuQEngine(), 24000
        init_seconds = time.perf_counter() - start
        result = {'engine': args.engine, 'initialization_seconds': init_seconds,
                  'network_connect_blocked': True, 'tracks': [],
                  'label_sha256': hashlib.sha256(json.dumps(engine.labels, sort_keys=True).encode()).hexdigest()}
        for source in args.files:
            source = source.resolve(strict=True)
            info = metadata(source)
            duration = info['length']
            if not .25 <= duration <= 600:
                raise ValueError('Each recording must be between .25 and 600 seconds')
            print(f'{args.engine}: {source.name}', flush=True)
            t = time.perf_counter()
            y, rate = decode(source, 0, duration, sr)
            semantic = engine.analyze(y, rate)
            elapsed = time.perf_counter() - t
            with source.open('rb') as f:
                sha = hashlib.file_digest(f, 'sha256').hexdigest()
            result['tracks'].append({'file': source.name, 'source_sha256': sha,
                'elapsed_seconds': elapsed, 'semantic': semantic})
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        # Known reference is a recognition sanity check, not an overall accuracy benchmark.
        import numpy as np
        assert engine.analyze(np.zeros(sr * 2, dtype=np.float32), sr)['status'] == 'insufficient_signal'
        assert engine.analyze(np.ones(sr, dtype=np.float32) * .1, sr)['status'] == 'insufficient_signal'
        reference = Path(__file__).resolve().parent / 'selftest/reference/sorohanro_-_solo-trumpet-06.ogg'
        if reference.exists():
            y, rate = decode(reference, 0, 10, sr)
            a, b = engine.scores(y, sr), engine.scores(y, sr)
            assert np.allclose(a, b, atol=1e-6)
            result['reference_check'] = {'instrument_candidates': engine.ranked(a, 5)['instruments'],
                'deterministic': True, 'silence_and_short_abstention': True}
        result['completed'] = True
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(args.output, flush=True)


if __name__ == '__main__':
    main()
