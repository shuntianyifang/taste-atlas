"""Download pinned public model files only. No audio is read or uploaded."""
import hashlib
import json
import time
from pathlib import Path

import requests
from model_config import REPO, REVISION, MODEL_DIR, WEIGHTS, CONFIG_FILES


def sha256(file):
    with file.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def main():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {'repo': REPO, 'revision': REVISION, 'files': {}}
    session = requests.Session()
    for name in [*CONFIG_FILES, *WEIGHTS]:
        target = MODEL_DIR / name
        target.parent.mkdir(parents=True, exist_ok=True)
        expected_size, expected_hash = WEIGHTS.get(name, (None, None))
        if target.exists() and expected_hash and target.stat().st_size == expected_size and sha256(target) == expected_hash:
            print(f'Verified existing {name}', flush=True)
        else:
            url = f'https://huggingface.co/{REPO}/resolve/{REVISION}/{name}'
            temporary = target.with_suffix(target.suffix + '.part')
            for attempt in range(3):
                try:
                    print(f'Downloading {name}', flush=True)
                    with session.get(url, stream=True, timeout=(30, 60)) as response:
                        response.raise_for_status()
                        with temporary.open('wb') as handle:
                            for chunk in response.iter_content(1024 * 1024):
                                handle.write(chunk)
                    if expected_size and temporary.stat().st_size != expected_size:
                        raise ValueError('Downloaded size mismatch')
                    if expected_hash and sha256(temporary) != expected_hash:
                        raise ValueError('Downloaded SHA-256 mismatch')
                    temporary.replace(target)
                    break
                except (requests.RequestException, OSError, ValueError):
                    if attempt == 2:
                        raise
                    time.sleep(2)
        manifest['files'][name] = {'bytes': target.stat().st_size, 'sha256': sha256(target)}
    manifest_path = MODEL_DIR / 'manifest.json'
    temporary_manifest = MODEL_DIR / 'manifest.json.part'
    temporary_manifest.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    temporary_manifest.replace(manifest_path)
    print('Pinned CLAP model ready for offline inference.', flush=True)


if __name__ == '__main__':
    main()
