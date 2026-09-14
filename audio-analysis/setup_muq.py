"""Download pinned public models only; never reads user audio."""
import hashlib
import json
from pathlib import Path
import requests
import time
import os
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parent
SPECS = {
    'muq-mulan': ('OpenMuQ/MuQ-MuLan-large', '2e01c796b71dca71b45251384c04cd7b237c9020', ['config.json', 'pytorch_model.bin', 'README.md']),
    'muq-backbone': ('OpenMuQ/MuQ-large-msd-iter', '0562a57814f6f8bbd9fdea0a25921a2fce1a841a', ['config.json', 'README.md']),
    'xlm-roberta-base': ('FacebookAI/xlm-roberta-base', 'e73636d4f797dec63c3081bb6ed5c7b0bb3f2089', ['config.json', 'tokenizer.json', 'tokenizer_config.json', 'sentencepiece.bpe.model', 'README.md']),
}


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def download_large(url, part, total):
    """Bounded concurrent HTTP ranges; append in order, retaining resumable prefix."""
    offset = part.stat().st_size if part.exists() else 0
    if offset > total:
        raise ValueError('Partial file exceeds expected size')
    block = 2 * 1024 * 1024
    if os.environ.get('MUQ_DOWNLOAD_MIRROR') == '1':
        url = url.replace('https://huggingface.co/', 'https://hf-mirror.com/')
    ranges = [(start, min(start + block, total) - 1) for start in range(offset, total, block)]

    def fetch(bounds):
        start, end = bounds
        for attempt in range(8):
            try:
                began = time.monotonic()
                with requests.get(url + f'?download=true&range={start}-{end}&attempt={attempt}',
                                  headers={'Range': f'bytes={start}-{end}'}, stream=True, timeout=(10, 15)) as r:
                    r.raise_for_status()
                    if r.status_code != 206 or r.headers.get('Content-Range') != f'bytes {start}-{end}/{total}':
                        raise ValueError('Server did not return the requested range')
                    pieces = []
                    for piece in r.iter_content(64 * 1024):
                        pieces.append(piece)
                        if time.monotonic() - began > 45:
                            raise requests.Timeout('Segment total time exceeded')
                    data = b''.join(pieces)
                    if len(data) != end - start + 1:
                        raise ValueError('Truncated HTTP range')
                    return data
            except requests.RequestException as exc:
                print(f'Range {start}: retry {attempt + 1} ({type(exc).__name__})', flush=True)
                if attempt == 7:
                    raise
                time.sleep(2)
    # Bounded parallel ranges, retaining at most 64 MB of block results.
    with ThreadPoolExecutor(max_workers=16) as pool, part.open('ab') as f:
        for i in range(0, len(ranges), 16):
            for data in pool.map(fetch, ranges[i:i + 16]):
                f.write(data)
                f.flush()
            print(f'  {part.name}: {f.tell() / 1e6:.0f}/{total / 1e6:.0f} MB', flush=True)


def main():
    manifest = {}
    for folder, (repo, revision, files) in SPECS.items():
        directory = ROOT / 'models' / folder
        directory.mkdir(parents=True, exist_ok=True)
        response = requests.get(f'https://huggingface.co/api/models/{repo}/tree/{revision}', timeout=60)
        response.raise_for_status()
        entries = {e['path']: e for e in response.json()}
        manifest[folder] = {'repo': repo, 'revision': revision, 'files': {}}
        for name in files:
            entry = entries[name]
            expected = entry.get('lfs', {}).get('oid')
            path = directory / name
            if not (path.exists() and path.stat().st_size == entry['size'] and (not expected or digest(path) == expected)):
                print(f'Downloading {repo}/{name}: {entry["size"] / 1e6:.1f} MB', flush=True)
                part = path.with_suffix(path.suffix + '.part')
                if entry['size'] > 32 * 1024 * 1024:
                    download_large(f'https://huggingface.co/{repo}/resolve/{revision}/{name}', part, entry['size'])
                for attempt in range(8):
                    offset = part.stat().st_size if part.exists() else 0
                    if offset == entry['size']:
                        break
                    try:
                        headers = {'Range': f'bytes={offset}-'} if offset else {}
                        with requests.get(f'https://huggingface.co/{repo}/resolve/{revision}/{name}?download=true&offset={offset}', headers=headers, stream=True, timeout=(30, 120)) as r:
                            r.raise_for_status()
                            if offset and r.status_code == 206 and not r.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                                raise ValueError('Unexpected resume range')
                            mode = 'ab' if offset and r.status_code == 206 else 'wb'
                            with part.open(mode) as f:
                                for chunk in r.iter_content(1024 * 1024):
                                    f.write(chunk)
                        break
                    except requests.RequestException:
                        if attempt == 7:
                            raise
                        print(f'Retrying {name} from saved bytes (attempt {attempt + 2})', flush=True)
                        time.sleep(2)
                if part.stat().st_size != entry['size'] or (expected and digest(part) != expected):
                    raise ValueError(f'Integrity failure: {name}')
                part.replace(path)
            manifest[folder]['files'][name] = {'bytes': path.stat().st_size, 'sha256': digest(path)}
    (ROOT / 'models' / 'muq-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Pinned MuQ models verified.', flush=True)


if __name__ == '__main__':
    main()
