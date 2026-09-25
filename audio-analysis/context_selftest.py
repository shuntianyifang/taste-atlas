"""Context-report provenance and local HTTP feedback regression checks."""
import copy
import json
import tempfile
import threading
import unittest
import http.client
from functools import partial
from pathlib import Path
from http.server import ThreadingHTTPServer
from context_report import fingerprint, validate_feedback, write, build, digest, read
from serve_audio import Handler


class ContextTests(unittest.TestCase):
    def test_build_and_changed_inputs(self):
        import soundfile as sf
        import numpy as np
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);sf.write(p/'audio.wav',np.zeros(8000),8000,subtype='PCM_16')
            write(p/'evidence.json',{'measurement':1})
            spec=dict(slug='test',title='<test>',source='audio.wav',source_sha256=digest(p/'audio.wav'),audio='audio.wav',audio_sha256=digest(p/'audio.wav'),listening_range=[10,11],liked_range=[10.2,10.8],gain_db=0,explanation=['</script>'],limitations=['未核对'],basis_note='依据',evidence=[dict(path='evidence.json',sha256=digest(p/'evidence.json'))],timeline=[dict(start=10,end=11,text='候选',evidence=[0])])
            write(p/'spec.json',spec);build([p/'spec.json'],p/'output')
            report=read(p/'output/test/context.json');self.assertEqual(report['report_id'],fingerprint(report))
            page=(p/'output/test/player.html').read_text(encoding='utf8')
            self.assertIn('&lt;/script&gt;',page);self.assertNotIn('<audio controls',page)
            with self.assertRaises(FileExistsError):build([p/'spec.json'],p/'output')
            write(p/'evidence.json',{'measurement':2})
            with self.assertRaises(ValueError):build([p/'spec.json'],p/'changed')
            spec['audio_sha256']='0'*64;write(p/'spec.json',spec)
            with self.assertRaises(ValueError):build([p/'spec.json'],p/'bad-audio')

    def fixture(self):
        r=dict(source_sha256='a'*64,listening_range=[120,180],liked_range=[140,160],explanation=['待核对解释'])
        r['report_id']=fingerprint(r)
        f=dict(schema_version=1,kind='context_interpretation',report_id=r['report_id'],source_sha256=r['source_sha256'],listening_range=r['listening_range'],liked_range=r['liked_range'],assessment='有',note='整体说到点上')
        return r,f

    def test_provenance_and_scope(self):
        r,f=self.fixture();self.assertEqual(validate_feedback(f,r),f)
        for key,value in [('report_id','b'*64),('listening_range',[121,180]),('assessment','喜欢'),('note','x'*2001)]:
            bad=copy.deepcopy(f);bad[key]=value
            with self.assertRaises(ValueError):validate_feedback(bad,r)
        r['explanation']=['修改后的解释']
        with self.assertRaises(ValueError):validate_feedback(f,r)

    def test_http(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'test').mkdir();r,f=self.fixture()
            write(root/'test/context.json',r);write(root/'context-index.json',dict(reports=[dict(slug='test',report_id=r['report_id'])]))
            server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=folder))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def post(value,origin):
                c=http.client.HTTPConnection('127.0.0.1',server.server_port)
                c.request('POST','/__context_feedback',body=json.dumps(value).encode(),headers={'Content-Type':'application/json','Origin':origin})
                response=c.getresponse();status=response.status;body=response.read();c.close();return status,body
            try:
                origin=f'http://127.0.0.1:{server.server_port}'
                self.assertEqual(post(f,'https://example.com')[0],403)
                self.assertEqual(post({**f,'report_id':'b'*64},origin)[0],400)
                status,body=post(f,origin);self.assertEqual(status,201)
                saved=json.loads(body);self.assertEqual(json.loads((root/'listening-exports'/saved['file']).read_text(encoding='utf8')),f)
                r['explanation']=['changed'];write(root/'test/context.json',r)
                self.assertEqual(post(f,origin)[0],400)
            finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
