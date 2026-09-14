"""Check real Git ignore behavior and source-only ZIP without creating a project repo."""
from pathlib import Path
import json
import subprocess
import tempfile
import zipfile
import source_release

def main():
    root=source_release.ROOT
    names=source_release.validate()
    with tempfile.TemporaryDirectory(prefix='taste-release-audit-') as directory:
        repo=Path(directory)/'git-audit'
        subprocess.run(['git','init','--quiet',str(repo)],check=True)
        git=['git','--git-dir='+str(repo/'.git'),'--work-tree='+str(root)]
        actual=subprocess.check_output(git+['ls-files','--others','--exclude-standard','-z']).decode().split(chr(0))
        assert set(filter(None,actual)) == set(names), 'Git candidates differ from source allowlist'
        probes=['tmp/test.mp3','audio-analysis/models/test.onnx','audio-analysis/.venv/Scripts/python.exe',
                'audio-analysis/results/private.json','audio-analysis/selftest/reference/test.ogg',
                'audio-analysis/.reference-essentia-js/node_modules/test.js','private.png','.env',
                'audio-analysis/new-secret.json','COPY_MANIFEST.json']
        ignored=subprocess.check_output(git+['check-ignore','--no-index','--stdin','-z'],
                                       input=(chr(0).join(probes)+chr(0)).encode()).decode().split(chr(0))
        assert set(filter(None,ignored)) == set(probes), 'Local data not ignored'
        archive=Path(directory)/'source.zip'
        subprocess.run([__import__('sys').executable,'-B',str(root/'tools/source_release.py'),'--output',str(archive)],check=True)
        with zipfile.ZipFile(archive) as z:
            assert len(z.namelist()) == len(names) and set(z.namelist()) == set(names)
            assert not any(name in probes for name in z.namelist())
        # No-clobber behavior must reject an existing output.
        result=subprocess.run([__import__('sys').executable,'-B',str(root/'tools/source_release.py'),'--output',str(archive)],capture_output=True)
        assert result.returncode != 0 and b'Output already exists' in result.stderr
    print('PASS: Git candidates, private-data probes, ZIP contents, existing-output refusal')

if __name__ == '__main__': main()
