"""Package evidence-linked, authored context explanations; no automatic causal inference."""
import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def fingerprint(report):
    return hashlib.sha256(json.dumps({k:v for k,v in report.items() if k!='report_id'}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def bounds(value):
    if not isinstance(value, list) or len(value)!=2 or any(type(x) not in (int,float) or not math.isfinite(x) for x in value) or not 0<=value[0]<value[1]<=86400:
        raise ValueError('Invalid interval')
    return value


def validate_feedback(value, report):
    if not isinstance(value,dict) or value.get('schema_version')!=1 or value.get('kind')!='context_interpretation':
        raise ValueError('Invalid context feedback')
    if fingerprint(report)!=report['report_id']:
        raise ValueError('Changed report')
    for k in ('report_id','source_sha256','listening_range','liked_range'):
        if value.get(k)!=report[k]:raise ValueError('Feedback provenance mismatch')
    if value.get('assessment') not in ('未评价','有','部分有','没有'):raise ValueError('Invalid assessment')
    if not isinstance(value.get('note'),str) or len(value['note'])>2000:raise ValueError('Invalid note')
    return {k:value[k] for k in ('schema_version','kind','report_id','source_sha256','listening_range','liked_range','assessment','note')}


def load_served_report(root, report_id):
    root=Path(root).resolve()
    index=read(root/'context-index.json')
    entry=next((e for e in index['reports'] if e['report_id']==report_id),None)
    if entry is None or not re.fullmatch('[a-z0-9-]{1,80}',entry['slug']):raise ValueError('Unknown context report')
    path=(root/entry['slug']/'context.json').resolve()
    if not path.is_relative_to(root):raise ValueError('Unsafe report path')
    return read(path)


def render(folder, report):
    from deep_analysis import render_player
    a,b=report['listening_range']
    data=dict(source=dict(name=report['title'],sha256=report['source_sha256']),
        range=dict(start=a,end=b,duration=b-a),listening=dict(shared_gain_db=report['gain_db'],tracks={'original':{'path':'context.wav'}}),
        tonal={'chords':[]},separation={'stems':[]},structure={'segments':[],'repeat_candidates':[]})
    render_player(folder,data)
    page=(folder/'player.html').read_text(encoding='utf8')
    page=page.replace('<title>本地音乐分析与试听</title>','<title>上下文听感报告</title>')
    page=page.replace('<p id="source">','<p id="source" hidden>')
    esc=html.escape
    intro=f'<h1>{esc(report["title"])}</h1><p><a href="../index.html">换一份报告</a></p><p>先读解释，再连续听。只需判断有没有说到你在意的地方。</p>'
    intro+='<section><h2>这段音乐怎样发展</h2>'+''.join('<p>'+esc(t)+'</p>' for t in report['explanation'])+'</section>'
    page=page.replace('<h1>音乐的结构与层次</h1>',intro)
    page=page.replace('<p class="warn">','<p class="warn" hidden>')
    page=page.replace('<label>试听声部','<label hidden>试听声部')
    page=page.replace('<p id="chord">','<p id="chord" hidden>')
    for heading in ('变化段落','相似片段 A / B 对照','你的标记'):
        page=page.replace('<section><h2>'+heading+'</h2>','<section hidden><h2>'+heading+'</h2>')
    page=page.replace('<section><img src="overview.png" alt="自相似、结构变化和原始声道能量图"></section>','')
    stamp=lambda t:f'{int(t)//60}:{int(t)%60:02d}'
    extra=f'<p>连续试听 {stamp(a)}–{stamp(b)}；你原先喜欢的范围是 {stamp(report["liked_range"][0])}–{stamp(report["liked_range"][1])}。</p>'
    extra+='<section><h2>这段解释说到你在意的地方了吗？</h2><p>这是对解释的评价，不改动歌曲喜好，也不证明喜欢的原因。</p><div id="context-ratings"></div><label>想补充的话（可留空）<textarea id="context-note" maxlength="2000" rows="2"></textarea></label><button id="context-save">保存这次反馈</button><p id="context-status" role="status"></p><details><summary>导出备份</summary><textarea id="context-json" readonly rows="6"></textarea><a id="context-download" hidden>下载反馈</a></details></section>'
    if report.get('history'):
        h=report['history'];extra+=f'<details><summary>此前对话记录</summary><p>对此前整段解释的回答：{esc(h["answer_verbatim"])}。这是历史记录，不自动当作本页新反馈，也不逐项确认分析。</p></details>'
    extra+='<details><summary>展开时间路线、依据与不确定之处</summary>'
    for item in report['timeline']:
        extra+=f'<p><b>{stamp(item["start"])}–{stamp(item["end"])}</b> {esc(item["text"])}</p>'
        extra+='<p>'+''.join(f'<a href="{report["evidence"][i]["file"]}">依据 {i+1}</a> ' for i in item['evidence'])+'</p>'
    extra+='<p>'+esc(report['basis_note'])+'</p>'+''.join('<p>'+esc(t)+'</p>' for t in report['limitations'])+'</details>'
    payload=json.dumps(report,ensure_ascii=False).replace('<','\\u003c')
    page=page.replace('</html>',extra+'<script>const contextReport='+payload+';</script><script>'+(ROOT/'context_controls.js').read_text(encoding='utf8')+'</script></html>')
    page=page.replace('</style>','a{color:#8ed2ff}body{max-width:760px}textarea{display:block;width:95%;font:inherit;margin:12px 0}summary{cursor:pointer;padding:14px 0}button[aria-pressed="true"]{background:#307a6b}details{margin:12px 0}</style>')
    (folder/'player.html').write_text(page,encoding='utf8')


def build(spec_paths, output):
    """Narrative is supplied by an analyst; evidence files and audio are verified locally."""
    import soundfile as sf
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    entries=[]
    for path in spec_paths:
        path=Path(path).resolve();spec=read(path);base=path.parent
        local=lambda key:(base/spec[key]).resolve()
        slug=spec['slug']
        if not re.fullmatch('[a-z0-9-]{1,80}',slug) or any(e['slug']==slug for e in entries):raise ValueError('Invalid or duplicate slug')
        a,b=bounds(spec['listening_range']);c,d=bounds(spec['liked_range'])
        if not a<=c<d<=b or b-a>600:raise ValueError('Liked range outside listening context')
        for k in ('source_sha256','audio_sha256'):
            if not re.fullmatch('[0-9a-f]{64}',spec[k]):raise ValueError('Invalid hash')
        if digest(local('source'))!=spec['source_sha256'] or digest(local('audio'))!=spec['audio_sha256']:raise ValueError('Source/audio changed')
        info=sf.info(local('audio'))
        if info.format!='WAV' or info.subtype!='PCM_16' or abs(info.frames/info.samplerate-(b-a))>1/info.samplerate:raise ValueError('Audio format/duration mismatch')
        for k in ('title','basis_note'):
            if not isinstance(spec[k],str) or not spec[k].strip():raise ValueError('Missing text')
        for k in ('explanation','limitations'):
            if not isinstance(spec[k],list) or not spec[k] or any(not isinstance(s,str) or not s.strip() for s in spec[k]):raise ValueError('Missing narrative/limits')
        if not spec['evidence'] or not spec['timeline']:raise ValueError('Missing evidence')
        if type(spec['gain_db']) not in (int,float) or not math.isfinite(spec['gain_db']):raise ValueError('Invalid gain')
        folder=output/slug;folder.mkdir()
        evidence=[]
        for i,e in enumerate(spec['evidence']):
            f=(base/e['path']).resolve()
            if f.suffix not in ('.json','.md','.csv') or digest(f)!=e['sha256']:raise ValueError('Evidence changed or unsupported')
            name=f'evidence-{i+1}{f.suffix}';shutil.copyfile(f,folder/name);evidence.append(dict(file=name,sha256=e['sha256']))
        for item in spec['timeline']:
            lo,hi=bounds([item['start'],item['end']])
            if not a<=lo<hi<=b or not isinstance(item['text'],str) or not item['text'].strip():raise ValueError('Invalid timeline')
            if not item['evidence'] or any(type(i)!=int or not 0<=i<len(evidence) for i in item['evidence']):raise ValueError('Missing evidence link')
        report={k:spec[k] for k in ('title','source_sha256','audio_sha256','listening_range','liked_range','gain_db','explanation','timeline','basis_note','limitations')}
        report.update(schema_version=1,kind='authored_context_report',evidence=evidence)
        if spec.get('history'):
            h=read(local('history'))
            if any(h.get(k)!=report[k] for k in ('source_sha256','liked_range','listening_range')) or h.get('provenance')!='direct_user_conversation' or h.get('answer_verbatim') not in ('有','部分有','没有'):raise ValueError('History provenance mismatch')
            report['history']={'answer_verbatim':h['answer_verbatim'],'sha256':digest(local('history'))}
        report['report_id']=fingerprint(report)
        shutil.copyfile(local('audio'),folder/'context.wav')
        if digest(folder/'context.wav')!=report['audio_sha256']:raise ValueError('Copy changed')
        write(folder/'context.json',report);render(folder,report)
        entries.append(dict(slug=slug,title=spec['title'],report_id=report['report_id']))
    write(output/'context-index.json',dict(schema_version=1,reports=entries))
    links=''.join(f'<li><a href="{e["slug"]}/player.html">{html.escape(e["title"])}</a></li>' for e in entries)
    (output/'index.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>上下文听感报告</title><style>body{font:18px system-ui;max-width:760px;margin:50px auto;padding:24px;background:#111922;color:#dde5ef}a{color:#8ed2ff}li{margin:24px 0}</style><h1>上下文听感报告</h1><p>选择一首，连续听，再评价整段解释。</p><ul>'+links+'</ul></html>',encoding='utf8')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('spec',type=Path,nargs='+');p.add_argument('--output',required=True,type=Path)
    args=p.parse_args();build(args.spec,args.output)
