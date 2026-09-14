"""Fetch versioned MTG models and pinned reference source; never reads music."""
import hashlib
import json
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
DIRECTORY = ROOT / 'models/essentia'
COMMIT = '66a890f285d0e1988155c12d17a2068e406cdd90'
MODELS = {
    'effnet': 'feature-extractors/discogs-effnet/discogs-effnet-bsdynamic-1',
    'instrument': 'classification-heads/mtg_jamendo_instrument/mtg_jamendo_instrument-discogs-effnet-1',
    'moodtheme': 'classification-heads/mtg_jamendo_moodtheme/mtg_jamendo_moodtheme-discogs-effnet-1',
    'musicnn': 'feature-extractors/musicnn/msd-musicnn-1',
    'deam': 'classification-heads/deam/deam-msd-musicnn-2',
}
SOURCES = ['spectral/tensorflowinputmusicnn.cpp', 'spectral/melbands.cpp',
           'spectral/melbands.h', 'spectral/triangularbands.cpp',
           'standard/windowing.cpp', 'standard/windowing.h',
           'standard/framecutter.cpp', 'standard/framecutter.h',
           'machinelearning/tensorflowpredicteffnetdiscogs.cpp',
           'machinelearning/tensorflowpredicteffnetdiscogs.h',
           'machinelearning/tensorflowpredictmusicnn.cpp',
           'machinelearning/tensorflowpredictmusicnn.h']


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    urls = {f'{key}.{ext}': f'https://essentia.upf.edu/models/{stem}.{ext}'
            for key, stem in MODELS.items() for ext in ('json', 'onnx')}
    urls.update({f'reference/{Path(s).name}': f'https://raw.githubusercontent.com/MTG/essentia/{COMMIT}/src/algorithms/{s}' for s in SOURCES})
    urls['reference/COPYING.txt'] = f'https://raw.githubusercontent.com/MTG/essentia/{COMMIT}/COPYING.txt'
    urls['MODEL-LICENSE.txt'] = 'https://essentia.upf.edu/models/LICENSE'
    manifest_path = DIRECTORY / 'manifest.json'
    old = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    files = {}
    for name, url in urls.items():
        p = DIRECTORY / name
        p.parent.mkdir(parents=True, exist_ok=True)
        record = old.get('files', {}).get(name, {})
        if not (p.exists() and record.get('url') == url and sha(p) == record.get('sha256')):
            for attempt in range(3):
                try:
                    r = requests.get(url, timeout=(20, 60)); r.raise_for_status()
                    temp = p.with_suffix(p.suffix + '.part')
                    temp.write_bytes(r.content)
                    temp.replace(p)
                    break
                except requests.RequestException:
                    if attempt == 2:
                        raise
            print('Fetched', name, p.stat().st_size, flush=True)
        files[name] = {'url': url, 'bytes': p.stat().st_size, 'sha256': sha(p)}
    manifest_path.write_text(json.dumps({'models': MODELS, 'reference_commit': COMMIT,
        'digest_provenance': 'SHA-256 computed from first official HTTPS download; not an upstream signed digest',
        'files': files}, indent=2), encoding='utf-8')
    print('Essentia assets ready.', flush=True)


if __name__ == '__main__':
    main()
