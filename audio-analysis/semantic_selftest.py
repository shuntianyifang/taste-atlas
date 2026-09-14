"""Offline functional checks, with one labeled instrument reference (not an accuracy benchmark)."""
import json
import socket
import unittest
from unittest.mock import patch

import numpy as np
import soundfile as sf

from analyze import ROOT, decode
from acoustics import timbre_features
from semantic import ClapEngine, clap_features


class AcousticTests(unittest.TestCase):
    def test_silence_and_tone(self):
        sr = 22050
        self.assertEqual(timbre_features(np.zeros(sr), sr)['status'], 'silence')
        t = np.arange(sr * 2) / sr
        value = timbre_features(.2 * np.sin(2 * np.pi * 440 * t), sr)
        self.assertLess(abs(value['median_spectral_centroid_hz'] - 440), 10)
        self.assertLess(value['median_spectral_flatness'], .02)

    def test_preprocessing_matches_librosa(self):
        import librosa
        y = np.random.default_rng(18).normal(0, .03, 48000 * 3).astype(np.float32)
        actual = clap_features(y)['input_features']
        padded = np.pad(np.tile(y, 3), (0, 48000))
        power = librosa.feature.melspectrogram(y=padded, sr=48000, n_fft=1024,
                                               hop_length=480, n_mels=64, fmin=50,
                                               fmax=14000, htk=False, norm='slaney', pad_mode='reflect')
        expected = librosa.power_to_db(power, ref=1, amin=1e-10, top_db=None).T[None, None]
        self.assertEqual(actual.shape, (1, 1, 1001, 64))
        np.testing.assert_allclose(actual, expected, atol=.002, rtol=0)
        with self.assertRaises(ValueError):
            clap_features(np.zeros(480001))


class SemanticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.network = patch.object(socket.socket, 'connect', side_effect=AssertionError('Unexpected network during inference'))
        cls.network.start()
        try:
            cls.engine = ClapEngine(threads=2)
        except Exception:
            cls.network.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.network.stop()

    def test_silence_and_short_segment_have_no_moods(self):
        for samples in [np.zeros(480000, dtype=np.float32), np.ones(48000, dtype=np.float32) * .1]:
            result = self.engine.analyze(samples, 48000)
            self.assertEqual(result['status'], 'insufficient_signal')
            self.assertEqual(result['overall_candidates'], {})
            self.assertEqual(result['analyzed_seconds'], 0)

    def test_known_trumpet_and_determinism(self):
        file = ROOT / 'selftest/reference/sorohanro_-_solo-trumpet-06.ogg'
        self.assertTrue(file.is_file(), 'Download the documented reference before this test; no fabricated fallback.')
        y, sr = decode(file, 0, 10, sample_rate=48000)
        first = self.engine.scores(y, sr)
        second = self.engine.scores(y, sr)
        np.testing.assert_allclose(first, second, atol=1e-6)
        ranking = self.engine.ranked(first)
        self.assertEqual(ranking['instruments'][0]['id'], 'brass')
        (ROOT / 'selftest/trumpet-recognition.json').write_text(json.dumps({
            'sample': file.name, 'source': 'librosa example: Mihai Sorohan - Trumpet loop',
            'expected_instrument_group': 'brass', 'ranking': ranking,
            'limitation': 'One labeled functional reference only; not a real-world accuracy benchmark.'
        }, ensure_ascii=False, indent=2), encoding='utf-8')

    def test_windows_use_source_timestamps_and_skip_tiny_tail(self):
        y, sr = decode(ROOT / 'selftest/reference/sorohanro_-_solo-trumpet-06.ogg', 0, 10, 48000)
        samples = np.resize(y, 48000 * 21)
        result = self.engine.analyze(samples, sr, source_start=80)
        self.assertEqual([(w['start_seconds'], w['end_seconds']) for w in result['windows']], [(80, 90), (90, 100), (100, 101)])
        self.assertEqual(result['analyzed_seconds'], 20)
        self.assertEqual(result['windows'][-1]['status'], 'insufficient_signal')
        self.assertIn('not a calibrated probability', result['score_type'])


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    (ROOT / 'selftest/semantic-verification.json').write_text(json.dumps({
        'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'success': result.wasSuccessful(), 'network_blocked_for_model_tests': True,
        'coverage': ['NumPy/librosa frontend parity', 'silence', 'short audio', 'known trumpet', 'deterministic inference', 'time windows'],
        'not_verified': ['multi-instrument ground truth accuracy', 'emotion ground truth accuracy', 'polyphonic transcription'],
    }, indent=2), encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
