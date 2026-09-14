"""DSP, offline inference, coverage and report verification (not an accuracy benchmark)."""
import copy
import json
from pathlib import Path
import shutil
import socket
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from analyze import ROOT, decode
from essentia_engine import logmel, patches, mel_filters, summarize, verify_assets, EssentiaEngine, DIRECTORY
from multi_model_report import validate


class FrontendTests(unittest.TestCase):
    def test_signals_and_independent_spectrum(self):
        from scipy.signal.windows import hann
        from scipy.fft import rfft
        n = 16000
        signals = [np.zeros(n), .1 * np.sin(2 * np.pi * 440 * np.arange(n) / 16000),
                   np.random.default_rng(7).normal(0, .01, n)]
        pulse = np.zeros(n); pulse[500] = .5; signals.append(pulse)
        for y in signals:
            actual = logmel(y)
            self.assertEqual(actual.shape, (64, 96))
            self.assertTrue(np.isfinite(actual).all())
            frame = np.pad(y.astype(np.float32), (256, 512))[256:768]
            power = abs(rfft(frame * hann(512, sym=True))) ** 2
            expected = np.log10(1 + 10000 * (mel_filters() @ power))
            np.testing.assert_allclose(actual[1], expected, atol=1e-5, rtol=1e-5)
        self.assertEqual(float(logmel(signals[0]).max()), 0.)
        # Independently derive Slaney triangular area-normalized filters.
        linear = np.linspace(0, 15 + np.log(8000 / 1000) / (np.log(6.4) / 27), 98)
        hz = np.where(linear < 15, linear * (200 / 3), 1000 * np.exp((linear - 15) * np.log(6.4) / 27))
        freq = np.arange(257) * 16000 / 512
        bank = []
        for lo, mid, hi in zip(hz, hz[1:], hz[2:]):
            bank.append(np.maximum(0, np.minimum((freq - lo) / (mid - lo), (hi - freq) / (hi - mid))) * 2 / (hi - lo))
        np.testing.assert_allclose(mel_filters(), bank, atol=1e-8)
        with self.assertRaises(ValueError):
            logmel(np.array([np.nan]))

    def test_patches_tail_and_overlap_weighting(self):
        y = np.ones(16000 * 4, dtype=np.float32) * .1
        for kind, size in [('effnet', 128), ('musicnn', 187)]:
            rows = list(patches(logmel(y), y, kind, 80))
            self.assertEqual(rows[0][0].shape, (size, 96))
            self.assertEqual(rows[0][1]['start_seconds'], 80)
            self.assertEqual(rows[-1][1]['end_seconds'], 84)
            self.assertGreater(rows[-1][1]['padded_frames'], 0)
        native = [{'start_seconds': 0, 'end_seconds': 3, 'status': 'analyzed', 'deam': {'valence': 2}},
                  {'start_seconds': 2, 'end_seconds': 5, 'status': 'analyzed', 'deam': {'valence': 8}}]
        self.assertAlmostEqual(summarize(native, 0, 4, 'deam')['valence'], 4.4)
        self.assertIsNone(summarize(native, 9, 10, 'deam'))

    def test_bad_assets_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.cache') as tmp:
            dest = Path(tmp) / 'models'
            shutil.copytree(DIRECTORY, dest)
            (dest / 'deam.onnx').write_bytes(b'corrupted')
            with self.assertRaises(ValueError):
                verify_assets(dest)
            (dest / 'deam.onnx').unlink()
            with self.assertRaises(OSError):
                verify_assets(dest)

    def test_comparison_rejects_mixed_runs(self):
        d = {'completed': True, 'label_sha256': 'x', 'tracks': [{'source_sha256': 'source',
             'semantic': {'selected_seconds': 10, 'windows': [{'start_seconds': 0, 'end_seconds': 10}]}}]}
        for scenario in ('source', 'time', 'incomplete', 'labels'):
            other = copy.deepcopy(d)
            if scenario == 'source': other['tracks'][0]['source_sha256'] = 'wrong'
            elif scenario == 'time': other['tracks'][0]['semantic']['windows'][0]['start_seconds'] = 1
            elif scenario == 'incomplete': other['completed'] = False
            else: other['label_sha256'] = 'wrong'
            with self.assertRaises(ValueError): validate({'clap': d, 'muq': other})


class InferenceTests(unittest.TestCase):
    def test_offline_reference_and_reports(self):
        from essentia_reporting import write_track, ZH
        with patch.object(socket.socket, 'connect', side_effect=RuntimeError('offline test')):
            engine = EssentiaEngine()
            self.assertTrue(all(label in ZH for labels in engine.labels['groups'].values() for label in labels))
            self.assertEqual(engine.analyze(np.zeros(32000))['status'], 'insufficient_signal')
            self.assertEqual(engine.analyze(np.ones(16000))['status'], 'insufficient_signal')
            ref = ROOT / 'selftest/reference/sorohanro_-_solo-trumpet-06.ogg'
            y, sr = decode(ref, 0, 10, 16000)
            a, b = engine.analyze(y, sr), engine.analyze(y, sr)
            self.assertEqual(a['overall'], b['overall'])
            self.assertEqual(len(a['overall']['instrument']), 40)
            self.assertEqual(len(a['overall']['moodtheme']), 56)
            self.assertEqual(set(a['overall']['deam']), {'valence', 'arousal'})
            out = ROOT / 'selftest/essentia-reference'
            track = {'file': ref.name, 'semantic': a, 'elapsed_seconds': 0}
            write_track(track, out)
            for name in ('report.md', 'report.json', 'timeline.csv', 'emotion.png'):
                self.assertGreater((out / name).stat().st_size, 100)
            (out / 'verification.json').write_text(json.dumps({'offline': True, 'deterministic': True,
                'silence_short_abstention': True, 'instrument_ranking': sorted(a['overall']['instrument'].items(), key=lambda x: -x[1]),
                'reference_runtime_parity': 'not_verified'}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    unittest.main(verbosity=2)
