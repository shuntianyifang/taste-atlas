"""Loopback-only static preview with byte ranges for audio seeking."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import json
import math
import uuid
from datetime import datetime, timezone


def validate_marks(value):
    if not isinstance(value,dict) or value.get('schema_version')!=1:
        raise ValueError('Invalid schema')
    if not re.fullmatch('[0-9a-f]{64}',str(value.get('source_sha256',''))):
        raise ValueError('Invalid source fingerprint')
    bounds=value.get('range',{})
    if not isinstance(bounds,dict) or any(type(bounds.get(k)) not in (int,float) or not math.isfinite(bounds[k]) for k in ['start','end','duration']):
        raise ValueError('Invalid range')
    if bounds['start']<0 or not 0<bounds['duration']<=600 or abs(bounds['end']-bounds['start']-bounds['duration'])>1e-6:
        raise ValueError('Invalid range')
    marks=value.get('marks')
    if not isinstance(marks,list) or len(marks)>1000:raise ValueError('Invalid marks')
    for mark in marks:
        if not isinstance(mark,dict) or type(mark.get('time')) not in (int,float) or not math.isfinite(mark['time']) or not bounds['start']<=mark['time']<=bounds['end']:
            raise ValueError('Invalid mark time')
        if mark.get('label') not in ('喜欢','不喜欢') or not isinstance(mark.get('track'),str) or len(mark['track'])>100:
            raise ValueError('Invalid mark')
    return {'schema_version':1,'source_sha256':value['source_sha256'],'range':{k:bounds[k] for k in ['start','end','duration']},
            'marks':[{k:m[k] for k in ['time','label','track']} for m in marks]}


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        if self.path.endswith('.html') or self.path.startswith('/__listening_marks') or self.path.startswith('/listening-exports/'):
            self.send_header('Cache-Control','no-store')
        if self.path.startswith('/listening-exports/') and self.path.endswith('.json'):
            self.send_header('Content-Disposition','attachment; filename="'+Path(self.path).name+'"')
        super().end_headers()

    def do_POST(self):
        if self.path not in ('/__listening_marks','/__fragment_feedback','/__context_feedback'):self.send_error(404);return
        # Same-origin loopback UI only; no filesystem path or arbitrary content accepted.
        if self.headers.get('Origin')!=f'http://127.0.0.1:{self.server.server_port}':
            self.send_error(403);return
        if self.headers.get_content_type()!='application/json':self.send_error(415);return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=262144:raise ValueError('Invalid size')
            payload=json.loads(self.rfile.read(size))
            if self.path=='/__context_feedback':
                from context_report import validate_feedback, load_served_report
                if not isinstance(payload,dict):raise ValueError('Invalid payload')
                report=load_served_report(self.directory,payload.get('report_id'))
                value=validate_feedback(payload,report)
            elif self.path=='/__fragment_feedback':
                from fragment_report import validate_feedback, preference_pairs
                value=validate_feedback(payload)
                report_path=Path(self.directory)/'fragments.json'
                if not report_path.is_file():raise ValueError('No fragment report served')
                report=json.loads(report_path.read_text(encoding='utf8'))
                if not report.get('completed'):raise ValueError('Incomplete fragment report')
                preference_pairs(report,value)
            else:value=validate_marks(payload)
        except (ValueError,TypeError,KeyError,OSError):self.send_error(400);return
        root=Path(self.directory).resolve();folder=root/'listening-exports'
        if not folder.resolve().is_relative_to(root):self.send_error(403);return
        folder.mkdir(exist_ok=True)
        prefix={'/__fragment_feedback':'fragment-feedback-','/__context_feedback':'context-feedback-','/__listening_marks':'listening-marks-'}[self.path]
        name=prefix+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.json'
        with (folder/name).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)
        body=json.dumps({'url':'/listening-exports/'+name,'file':name}).encode()
        self.send_response(201);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

    def send_head(self):
        self.remaining=None
        path=Path(self.translate_path(self.path))
        if not path.is_file() or 'Range' not in self.headers:
            return super().send_head()
        size=path.stat().st_size
        match=re.fullmatch(r'bytes=(\d+)-(\d*)',self.headers['Range'])
        if not match:
            self.send_error(416);return None
        start=int(match[1]);end=int(match[2]) if match[2] else size-1
        if start>=size or start>end:
            self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return None
        end=min(end,size-1);f=path.open('rb');f.seek(start);self.remaining=end-start+1
        self.send_response(206);self.send_header('Content-Type',self.guess_type(str(path)))
        self.send_header('Accept-Ranges','bytes');self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.send_header('Content-Length',str(self.remaining));self.end_headers();return f

    def copyfile(self,source,outputfile):
        try:
            if self.remaining is None:return super().copyfile(source,outputfile)
            while self.remaining:
                block=source.read(min(65536,self.remaining))
                if not block:break
                outputfile.write(block);self.remaining-=len(block)
        except (ConnectionResetError,ConnectionAbortedError,BrokenPipeError):pass


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--port',type=int,default=8876)
    args=p.parse_args();root=args.directory.resolve()
    if not root.is_dir():raise ValueError('Missing directory')
    print(f'http://127.0.0.1:{args.port}/ — Ctrl+C to stop',flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),partial(Handler,directory=str(root))).serve_forever()
