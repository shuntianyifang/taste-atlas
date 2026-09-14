"""Contract and deterministic offline inference tests; not separation accuracy."""
import json
import shutil
import socket
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import numpy as np
import soundfile as sf
from deep_analysis import ROOT, digest, write_json, offline
from separate_audio import verify_model, verify_input


class SeparationTests(unittest.TestCase):
    def test_missing_and_corrupt_model(self):
        path,manifest=verify_model()
        with tempfile.TemporaryDirectory(dir=ROOT/'selftest') as temp:
            out=Path(temp);write_json(out/'manifest.json',manifest)
            with self.assertRaises(FileNotFoundError):verify_model(out)
            (out/path.name).write_bytes(b'broken')
            with self.assertRaises(ValueError):verify_model(out)
            altered=dict(manifest);altered['file']='../other.th';write_json(out/'manifest.json',altered)
            with self.assertRaises(ValueError):verify_model(out)

    def test_input_contract(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'selftest') as temp:
            out=Path(temp);sr=8000;audio=np.zeros((sr*3,2),dtype=np.float32)
            sf.write(out/'original.wav',audio,sr,subtype='FLOAT');shutil.copy2(out/'original.wav',out/'source.wav')
            result={'completed':True,'decoded_sha256':digest(out/'source.wav'),
                    'source':{'path':str(out/'original.wav'),'sha256':digest(out/'original.wav'),'sample_rate':sr,'channels':2},
                    'range':{'start':80,'end':83,'duration':3},'separation':{'status':'not_run'}}
            write_json(out/'report.json',result);verify_input(out)
            for changes in [{'completed':False},{'decoded_sha256':'wrong'},{'range':{'start':80,'end':84,'duration':3}},
                            {'range':{'start':0,'end':601,'duration':601}},{'separation':{'status':'completed'}}]:
                write_json(out/'report.json',{**result,**changes})
                with self.assertRaises(ValueError):verify_input(out)
            write_json(out/'report.json',result)
            (out/'original.wav').write_bytes(b'changed')
            with self.assertRaises(ValueError):verify_input(out)

    def test_deterministic_offline_model(self):
        import torch
        from demucs.states import load_model
        from demucs.apply import apply_model
        path,manifest=verify_model();torch.set_num_threads(4)
        with patch.object(socket.socket,'connect',offline),patch.object(socket,'create_connection',offline):
            model=load_model(torch.load(path,map_location='cpu',weights_only=False),strict=True).eval()
            self.assertEqual(model.sources,['drums','bass','other','vocals'])
            x=torch.from_numpy(np.random.default_rng(42).normal(0,.02,(1,2,44100*2)).astype(np.float32))
            with torch.inference_mode():
                a=apply_model(model,x,device='cpu',shifts=0,split=True,segment=7.8,overlap=.25)
                b=apply_model(model,x,device='cpu',shifts=0,split=True,segment=7.8,overlap=.25)
            self.assertEqual(tuple(a.shape),(1,4,2,88200));self.assertTrue(torch.isfinite(a).all())
            self.assertTrue(torch.equal(a,b))
            write_json(ROOT/'selftest/separation-verification.json',{'offline':True,'deterministic':True,
                'shape':list(a.shape),'model_sha256':manifest['sha256'],'accuracy_evaluated':False})


if __name__=='__main__':unittest.main()
