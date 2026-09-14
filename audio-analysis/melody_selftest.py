"""Known-pitch WASM smoke checks, not real-song melody accuracy."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import numpy as np
from deep_analysis import ROOT,write_json


class MelodyTests(unittest.TestCase):
    def test_tone_silence_and_determinism(self):
        sr=44100;t=np.arange(sr*3)/sr;signal=(.2*np.sin(2*np.pi*440*t)).astype('<f4')
        with tempfile.TemporaryDirectory(dir=ROOT/'selftest') as folder:
            folder=Path(folder);source=folder/'input.f32';output=folder/'out.json'
            def run(y):
                y.tofile(source)
                subprocess.run(['node',str(ROOT/'melodia.cjs'),str(source),str(output)],check=True,timeout=120,capture_output=True)
                return json.loads(output.read_text(encoding='utf8'))
            a=run(signal);b=run(signal)
            self.assertEqual(a['pitch'],b['pitch']);self.assertEqual(a['confidence'],b['confidence'])
            hz=np.array(a['pitch']);active=hz[hz>0]
            self.assertGreater(len(active),300);self.assertLess(abs(np.median(active)-440),3)
            self.assertTrue(abs(len(hz)-len(signal)/128)<=2)
            silent=run(np.zeros_like(signal));self.assertTrue(all(x==0 for x in silent['pitch']))
            self.assertEqual(silent['abstention'],'silence_before_algorithm')
            write_json(ROOT/'selftest/melody-verification.json',{'offline':True,'deterministic':True,
                'tone_440_median_hz':float(np.median(active)),'silence_abstained':True,'real_music_accuracy_evaluated':False})


if __name__=='__main__':unittest.main()
