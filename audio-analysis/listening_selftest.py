"""Guard evidence boundaries in listening summaries."""
import unittest
from listening_summary import listening_summary


class ListeningTests(unittest.TestCase):
    def test_weak_and_missing(self):
        text = '\n'.join(listening_summary({'overall_candidates': {'mood': {
            'assessment': 'weak_match', 'candidates': [{'label': '不应成为结论'}]}}}))
        self.assertNotIn('不应成为结论', text)
        self.assertIn('无有效时间证据', text)

    def test_gaps_silence_and_source_offsets(self):
        def window(a, b, status='analyzed'):
            return dict(start_seconds=a, end_seconds=b, status=status,
                        candidates={'mood': [{'label': '梦幻'}], 'timbre': [{'label': '绵长'}]})
        text = '\n'.join(listening_summary({'windows': [window(70, 80), window(80, 90),
            window(90, 100, 'insufficient_signal'), window(100, 110), window(120, 125.5)]}))
        self.assertIn('01:10.00–01:30.00', text)
        self.assertIn('01:30.00–01:40.00 | 证据不足', text)
        self.assertIn('01:40.00–01:50.00', text)
        self.assertIn('02:00.00–02:05.50', text)

    def test_close_candidates_retained(self):
        text = '\n'.join(listening_summary({'overall_candidates': {'mood': {
            'assessment': 'close_candidates', 'candidates': [{'label': '平静'}, {'label': '激烈'}]}}}))
        self.assertIn('平静；激烈', text)
        self.assertIn('不能确定主导感觉', text)


if __name__ == '__main__':
    unittest.main()
