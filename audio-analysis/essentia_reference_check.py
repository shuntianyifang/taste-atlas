"""Compare per-frame preprocessing with Essentia.js 0.1.3 WASM."""
import json
import subprocess
import numpy as np
from analyze import ROOT, decode
from essentia_engine import logmel


def main():
    signals = {'silence': np.zeros(16000), 'tone': .1 * np.sin(2 * np.pi * 440 * np.arange(16000) / 16000),
               'noise': np.random.default_rng(7).normal(0, .01, 16000)}
    signals['impulse'] = np.zeros(16000); signals['impulse'][500] = .5
    signals['trumpet'], _ = decode(ROOT / 'selftest/reference/sorohanro_-_solo-trumpet-06.ogg', 0, 4, 16000)
    frames, expected, identifiers = [], [], []
    for key, signal in signals.items():
        y = signal.astype(np.float32)
        padded = np.pad(y, (256, 512))
        mel = logmel(y)
        for i in sorted(set([0, 1, 2, 20, len(mel) - 1])):
            frames.append(padded[i * 256:i * 256 + 512].tolist())
            expected.append(mel[i]); identifiers.append(f'{key}:{i}')
    folder = ROOT / 'selftest/essentia-reference'
    folder.mkdir(parents=True, exist_ok=True)
    inp, out = folder / 'input-frames.json', folder / 'wasm-bands.json'
    inp.write_text(json.dumps(frames), encoding='utf-8')
    subprocess.run(['node', str(ROOT / 'essentia_reference.cjs'), str(inp), str(out)], check=True)
    actual = np.asarray(json.loads(out.read_text()))
    errors = np.max(np.abs(actual - np.asarray(expected)), axis=1)
    record = {'runtime': 'official essentia.js 0.1.3 WASM', 'scope': 'TensorflowInputMusiCNN per-frame only',
              'max_absolute_error': float(errors.max()), 'tolerance': 1e-4,
              'passed': bool(errors.max() <= 1e-4), 'cases': dict(zip(identifiers, map(float, errors)))}
    (folder / 'wasm-verification.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps(record, indent=2))
    if not record['passed']:
        raise ValueError('WASM reference differs; investigate preprocessing')


if __name__ == '__main__':
    main()
