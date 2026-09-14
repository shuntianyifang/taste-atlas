"""Verify loopback HTTP seeking; does not claim browser playback acceptance."""
import http.client
import tempfile
import threading
import unittest
import json
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from deep_analysis import ROOT
from serve_audio import Handler


class PreviewTests(unittest.TestCase):
    def test_ranges_and_missing(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'selftest') as folder:
            path=Path(folder)/'audio.wav';data=bytes(range(256))*32;path.write_bytes(data)
            server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=folder))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                def get(url,method='GET',headers=None):
                    conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                    conn.request(method,url,headers=headers or {});response=conn.getresponse()
                    status=response.status;headers=dict(response.getheaders());body=response.read();conn.close();return status,headers,body
                self.assertEqual(get('/missing')[0],404)
                self.assertEqual(get('/audio.wav')[2],data)
                status,headers,body=get('/audio.wav',headers={'Range':'bytes=2048-4095'})
                self.assertEqual(status,206);self.assertEqual(body,data[2048:4096])
                self.assertEqual(headers['Content-Range'],'bytes 2048-4095/8192')
                status,headers,body=get('/audio.wav','HEAD',{'Range':'bytes=4096-'})
                self.assertEqual(status,206);self.assertEqual(body,b'');self.assertEqual(headers['Content-Length'],'4096')
                self.assertEqual(get('/audio.wav',headers={'Range':'bytes=999999-'})[0],416)
                body={'schema_version':1,'source_sha256':'a'*64,'range':{'start':80,'end':84,'duration':4},
                      'marks':[{'time':81.25,'label':'喜欢','track':'bass'}]}
                def post(value,origin):
                    conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                    conn.request('POST','/__listening_marks',body=json.dumps(value).encode(),headers={'Origin':origin,'Content-Type':'application/json'})
                    response=conn.getresponse();status=response.status;data=response.read();conn.close();return status,data
                origin=f'http://127.0.0.1:{server.server_port}'
                self.assertEqual(post(body,'https://example.com')[0],403)
                invalid={**body,'marks':[{'time':90,'label':'喜欢','track':'bass'}]}
                self.assertEqual(post(invalid,origin)[0],400)
                status,raw=post(body,origin);self.assertEqual(status,201)
                saved=json.loads(raw);status,headers,raw=get(saved['url'])
                self.assertEqual(status,200);self.assertEqual(json.loads(raw),body)
                self.assertIn('attachment;',headers['Content-Disposition'])
                self.assertEqual(json.loads((Path(folder)/'listening-exports'/saved['file']).read_text(encoding='utf8')),body)
            finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
