"""Verify comparison refuses mismatched experiments and handles silence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from compare_models import report, ROOT


class ComparisonTests(unittest.TestCase):
    def test_reject_mismatches_and_render_silence(self):
        (ROOT / '.cache').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / '.cache') as tmp:
            folder = Path(tmp)
            original = {'completed': True, 'initialization_seconds': 1, 'label_sha256': 'same',
                        'engine': 'clap', 'tracks': [{'file': 'silence.wav', 'source_sha256': 'same',
                        'elapsed_seconds': 1, 'semantic': {'selected_seconds': 2,
                        'overall_candidates': {}, 'windows': [{'start_seconds': 0,
                        'end_seconds': 2, 'status': 'insufficient_signal', 'candidates': {}}]}}]}
            def write(a, b):
                for name, obj in [('clap', a), ('muq', b)]:
                    (folder / f'{name}.json').write_text(json.dumps(obj), encoding='utf-8')
            write(original, original)
            report(folder)
            self.assertIn('不判断', (folder / 'comparison.md').read_text(encoding='utf-8'))
            for mutation in ('source', 'labels', 'window', 'incomplete'):
                changed = copy.deepcopy(original)
                if mutation == 'source':
                    changed['tracks'][0]['source_sha256'] = 'different'
                elif mutation == 'labels':
                    changed['label_sha256'] = 'different'
                elif mutation == 'window':
                    changed['tracks'][0]['semantic']['windows'][0]['start_seconds'] = .1
                else:
                    changed['completed'] = False
                write(original, changed)
                with self.assertRaises(ValueError, msg=mutation):
                    report(folder)


if __name__ == '__main__':
    unittest.main()
