"""Synthetic invariants, not real-music accuracy evaluation."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
from deep_analysis import ROOT, decode_native, loudness, render_player
from deep_features import structure, tonal, stereo_metrics, pitch_candidates
import soundfile as sf


class DeepTests(unittest.TestCase):
    def test_stereo(self):
        sr=8000;t=np.arange(sr*2)/sr;x=.1*np.sin(2*np.pi*440*t)
        same=stereo_metrics(np.column_stack([x,x]),sr,80)[0]
        self.assertAlmostEqual(same['lr_correlation'],1)
        self.assertIsNone(same['side_to_mid_db']);self.assertEqual(same['start'],80)
        anti=stereo_metrics(np.column_stack([x,-x]),sr)[0]
        self.assertAlmostEqual(anti['lr_correlation'],-1);self.assertIsNone(anti['side_to_mid_db'])
        self.assertIsNone(stereo_metrics(np.zeros((100,2)),sr)[0]['lr_correlation'])
        self.assertIsNone(stereo_metrics(x[:,None],sr)[0]['lr_correlation'])
        with self.assertRaises(ValueError): stereo_metrics(np.full((100,2),np.nan),sr)

    def test_harmony_and_silence(self):
        times=np.arange(200)/20;c=np.zeros((12,200));c[[0,4,7],:]=1
        result=tonal(c,times,np.ones(200),10,30)
        self.assertEqual(result['chords'][0]['candidate'],'C:maj')
        self.assertEqual(result['chords'][0]['start'],30)
        self.assertEqual(result['chords'][-1]['end'],40)
        silent=tonal(c*0,times,np.zeros(200),10)
        self.assertEqual(silent['global_key_candidates'],[])
        self.assertTrue(all(r['candidate']=='N/不确定' for r in silent['chords']))

    def test_aba_structure(self):
        times=np.arange(1200)/20;c=np.zeros((12,1200));c[[0,4,7],:400]=1;c[[1,5,8],400:800]=1;c[[0,4,7],800:]=1
        m=np.zeros((14,1200));m[1,:400]=2;m[2,400:800]=2;m[1,800:]=2
        st,sim=structure(c,m,times,60,10)
        starts=[r['start'] for r in st['segments']]
        self.assertTrue(any(abs(s-30)<2 for s in starts));self.assertTrue(any(abs(s-50)<2 for s in starts))
        self.assertTrue(any(r['start_a']<30 and r['start_b']>=50 for r in st['repeat_candidates']))
        self.assertEqual(st['segments'][-1]['end'],70);self.assertTrue(np.isfinite(sim).all())

    def test_pitch(self):
        sr=11025;t=np.arange(sr*3)/sr;x=.2*np.sin(2*np.pi*440*t)
        rows=pitch_candidates(x,sr,80);hz=[r['hz'] for r in rows if r['hz']]
        self.assertGreater(len(hz),50);self.assertLess(abs(np.median(hz)-440),3)
        self.assertTrue(all(80<=r['time']<83 for r in rows))
        self.assertEqual(pitch_candidates(np.zeros(sr*3),sr),[])
        bass=pitch_candidates(.2*np.sin(2*np.pi*55*t),sr,0,32.7,523.25)
        self.assertLess(abs(np.median([r['hz'] for r in bass if r['hz']])-55),1)

    def test_native_decode_and_loudness(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'selftest') as temp:
            temp=Path(temp);sr=48000;t=np.arange(sr*5)/sr;x=.1*np.sin(2*np.pi*440*t)
            source=temp/'test.wav';sf.write(source,np.column_stack([x,x/2]),sr,subtype='FLOAT')
            audio,rate=decode_native(source,1,3,temp/'selected.wav')
            self.assertEqual(rate,sr);self.assertEqual(audio.shape,(sr*3,2))
            measured=loudness(temp/'selected.wav');self.assertTrue(np.isfinite(measured['input_i']))
            self.assertAlmostEqual(measured['input_tp'],-20,delta=.2)


if __name__=='__main__': unittest.main()
