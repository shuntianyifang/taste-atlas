"""Regression tests for interval evidence and personal-feedback boundaries."""
import copy
import unittest
import tempfile
from pathlib import Path
from fragment_report import select_changes, validate_feedback, preference_pairs, window_evidence, merge_feedback, write


class FragmentTests(unittest.TestCase):
    def feedback(self):
        return dict(schema_version=2,report_id='b'*64,feedback=[dict(id='a-1',source_sha256='a'*64,
            start=10,end=30,reaction='无感',description_match='不符合',separation_quality='未核对',layer='人声',reason='声音太靠前')])

    def test_invalid_feedback(self):
        for field,value in [('start',float('nan')),('end',9),('reaction','很准'),('source_sha256','../file'),('reason','x'*2001)]:
            data=self.feedback();data['feedback'][0][field]=value
            with self.assertRaises(ValueError):validate_feedback(data)
        data=self.feedback();data['feedback']*=2
        with self.assertRaises(ValueError):validate_feedback(data)

    def test_reaction_independent_of_accuracy(self):
        row=validate_feedback(self.feedback())['feedback'][0]
        self.assertEqual(row['reaction'],'无感');self.assertEqual(row['description_match'],'不符合')

    def test_preference_provenance_and_unrated(self):
        data=self.feedback();c={**data['feedback'][0],'features':['clap:timbre:airy']}
        report=dict(report_id='b'*64,tracks=[dict(fragments=[c])])
        self.assertEqual(preference_pairs(report,data)['rated_count'],1)
        data['feedback'][0]['reaction']='未评价'
        self.assertEqual(preference_pairs(report,data)['rated_count'],0)
        data['feedback'][0]['start']=11
        with self.assertRaises(ValueError):preference_pairs(report,data)
        data=self.feedback();data['report_id']='c'*64
        with self.assertRaises(ValueError):preference_pairs(report,data)

    def test_opposite_reactions_same_feature(self):
        data=self.feedback();b=copy.deepcopy(data['feedback'][0]);b.update(id='a-2',start=40,end=60,reaction='喜欢');data['feedback'].append(b)
        report=dict(report_id='b'*64,tracks=[dict(fragments=[dict(x,features=['muq:timbre:airy']) for x in data['feedback']])])
        result=preference_pairs(report,data)
        self.assertEqual(len(result['pairs']),1);self.assertTrue(result['pairs'][0]['different_reactions'])

    def test_spacing_and_silence(self):
        def w(i,db):return dict(start=i*10,end=(i+1)*10,rms_dbfs=db,timbre=dict(median_spectral_centroid_hz=1000))
        rows=[w(i,-20 if i%2 else -10) for i in range(20)]
        chosen=select_changes(rows)
        self.assertEqual(len(chosen),4)
        self.assertTrue(all(b['boundary']-a['boundary']>=30 for a,b in zip(chosen,chosen[1:])))
        self.assertEqual(select_changes([w(i,-100) for i in range(10)]),[])
        self.assertEqual(select_changes([w(i,-20) for i in range(10)]),[])

    def test_offset_applied_once(self):
        models={'muq':dict(tracks=[dict(slug='pinnacle',source_start=600,semantic=dict(windows=[dict(start_seconds=0,end_seconds=10,status='analyzed',candidates={})]))])}
        evidence=window_evidence(models,'pinnacle',600,610)
        self.assertEqual(evidence[0]['start'],600)
        self.assertEqual(window_evidence(models,'pinnacle',0,10),[])

    def test_merge_latest_and_reject_foreign(self):
        first=self.feedback();latest=copy.deepcopy(first);latest['feedback'][0]['reaction']='喜欢'
        report=dict(report_id=first['report_id'],tracks=[dict(fragments=[dict(first['feedback'][0],features=[])])])
        with tempfile.TemporaryDirectory() as folder:
            a,b=Path(folder)/'a.json',Path(folder)/'b.json';write(a,first);write(b,latest)
            merged=merge_feedback(report,[a,b])
            self.assertEqual(len(merged['feedback']),1);self.assertEqual(merged['feedback'][0]['reaction'],'喜欢')
            latest['feedback'][0]['source_sha256']='f'*64;write(b,latest)
            with self.assertRaises(ValueError):merge_feedback(report,[a,b])


if __name__=='__main__':unittest.main()
