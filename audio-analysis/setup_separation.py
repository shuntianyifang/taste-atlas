"""Prepare official HTDemucs weights. Never reads audio. Inference is separate."""
import hashlib
import json
from pathlib import Path
import time
import requests

ROOT=Path(__file__).resolve().parent
MODEL='955717e8-8726e21a.th'
URL='https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/'+MODEL
COMMIT='ef66d254cd6d558e207eeff2c4b8d053db2e77dd'
SHA256='8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4'


def digest(path):
    with path.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    out=ROOT/'models/demucs';out.mkdir(parents=True,exist_ok=True)
    target=out/MODEL;part=target.with_suffix('.part')
    if not target.exists():
        for attempt in range(8):
            offset=part.stat().st_size if part.exists() else 0
            try:
                with requests.get(URL,headers={'Range':f'bytes={offset}-'} if offset else {},stream=True,timeout=(20,60)) as r:
                    r.raise_for_status()
                    if offset and r.status_code==206:
                        if not r.headers.get('Content-Range','').startswith(f'bytes {offset}-'):raise ValueError('Incorrect download range')
                        mode='ab'
                    else: mode='wb'
                    with part.open(mode) as f:
                        for block in r.iter_content(1024*1024): f.write(block)
                if digest(part)!=SHA256:raise ValueError('Pinned SHA-256 mismatch')
                part.replace(target);break
            except requests.RequestException:
                if attempt==7:raise
                time.sleep(2)
    sha=digest(target)
    if sha!=SHA256:raise ValueError('Pinned SHA-256 mismatch')
    commit=COMMIT
    assets=[]
    for relative in ['LICENSE','README.md','demucs/remote/files.txt','demucs/remote/htdemucs.yaml']:
        url=f'https://raw.githubusercontent.com/facebookresearch/demucs/{commit}/{relative}'
        response=requests.get(url,timeout=30);response.raise_for_status()
        path=out/(relative.replace('/','-'));path.write_bytes(response.content)
        assets.append({'path':path.name,'url':url,'sha256':digest(path),'bytes':path.stat().st_size})
    manifest={'model':'htdemucs','demucs_version':'4.0.1','source_commit':commit,'device':'cpu','precision':'float32',
              'file':MODEL,'url':URL,'bytes':target.stat().st_size,'sha256':sha,
              'upstream_sha256_prefix':'8726e21a','license':'MIT (see preserved upstream LICENSE)',
              'verification':'Official HTTPS + upstream 8-character digest prefix; full digest locally recorded.',
              'reference_assets':assets}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
