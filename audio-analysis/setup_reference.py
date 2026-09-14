"""Optional labeled reference and attribution from librosa's public example collection."""
import hashlib
import requests
from model_config import ROOT

FILES = {
    'sorohanro_-_solo-trumpet-06.ogg': '8374466fd3951d24509da6e799b132a0db0bdeda69d99c69d989a6888d3d727d',
    'sorohanro_-_solo-trumpet-06.txt': '750a191b9d0cc94b2f19cfbf11acc13783f75bedcccfcf562f5b076efd068aba',
}


def main():
    target = ROOT / 'selftest' / 'reference'
    target.mkdir(parents=True, exist_ok=True)
    for name, expected in FILES.items():
        file = target / name
        if file.is_file() and hashlib.sha256(file.read_bytes()).hexdigest() == expected:
            continue
        response = requests.get('https://librosa.org/data/audio/' + name, timeout=30)
        response.raise_for_status()
        if hashlib.sha256(response.content).hexdigest() != expected:
            raise ValueError('Reference SHA-256 mismatch')
        file.write_bytes(response.content)
    print('librosa trumpet reference and CC-BY attribution verified.')


if __name__ == '__main__':
    main()
