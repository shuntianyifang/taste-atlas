"""Build local, evidence-linked listening experiments from a reference bundle."""
import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def select_changes(windows, count=4):
    """Rank adjacent measured windows; no claim of semantic event detection."""
    candidates = []
    for before, after in zip(windows, windows[1:]):
        if abs(before['end'] - after['start']) > .01 or min(before['end']-before['start'], after['end']-after['start']) < 5:
            continue
        db = after['rms_dbfs'] - before['rms_dbfs']
        a = before['timbre']['median_spectral_centroid_hz']
        b = after['timbre']['median_spectral_centroid_hz']
        if not all(math.isfinite(v) for v in (db, a, b)) or min(a, b) <= 0:
            continue
        if max(before['rms_dbfs'], after['rms_dbfs']) < -60:
            continue
        ratio = math.log2(b/a)
        if abs(db)/3+abs(ratio)<.5:
            continue
        candidates.append(dict(start=before['start'], boundary=after['start'], end=after['end'],
            rms_delta_db=db, centroid_ratio=b/a, score=abs(db)/3+abs(ratio),
            before=before, after=after))
    selected = []
    for candidate in sorted(candidates, key=lambda c: (-c['score'], c['start'])):
        if all(abs(candidate['boundary']-x['boundary']) >= 30 for x in selected):
            selected.append(candidate)
        if len(selected) == count:
            break
    return sorted(selected, key=lambda c: c['start'])


def listening_clues(fragment):
    """Versioned listening questions, never an inferred reason for liking a passage."""
    clues = []
    db, ratio = fragment.get('rms_delta_db'), fragment.get('centroid_ratio')
    if isinstance(db, (int, float)) and math.isfinite(db) and abs(db) >= 2:
        clues.append(dict(feature='energy:up' if db > 0 else 'energy:down',
            text='后半段听起来力度更强。' if db > 0 else '后半段听起来力度收回了。',
            basis=f'后窗 RMS 相对前窗 {db:+.1f} dB；能量变化不等于主观响度或情绪。'))
    if isinstance(ratio, (int, float)) and math.isfinite(ratio) and (ratio >= 1.2 or 0 < ratio <= 1/1.2):
        clues.append(dict(feature='brightness:up' if ratio > 1 else 'brightness:down',
            text='后半段听起来更亮、更尖一些。' if ratio > 1 else '后半段听起来更暗、更柔一些。',
            basis=f'后窗频谱重心为前窗的 {ratio:.2f} 倍；配器、打击声等也可能影响测量。'))
    for clue in clues:
        clue.update(kind='sound_change', start=fragment['start'], boundary=fragment['boundary'], end=fragment['end'])
        identity=dict(version=1, source=fragment['source_sha256'], **clue)
        clue['id']=hashlib.sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return clues


def validate_feedback(value):
    if not isinstance(value, dict) or value.get('schema_version') not in (2, 3):
        raise ValueError('Invalid feedback schema')
    if not re.fullmatch(r'[0-9a-f]{64}', str(value.get('report_id', ''))):
        raise ValueError('Invalid report fingerprint')
    rows = value.get('feedback')
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValueError('Invalid feedback count')
    clean = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not re.fullmatch(r'[a-z0-9-]{1,90}', str(row.get('id', ''))) or row['id'] in seen:
            raise ValueError('Invalid or duplicate fragment')
        seen.add(row['id'])
        if not re.fullmatch(r'[0-9a-f]{64}', str(row.get('source_sha256', ''))):
            raise ValueError('Invalid source fingerprint')
        a, b = row.get('start'), row.get('end')
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in (a, b)) or not 0 <= a < b <= 86400:
            raise ValueError('Invalid interval')
        if row.get('reaction') not in ('未评价', '喜欢', '无感', '不喜欢'):
            raise ValueError('Invalid reaction')
        if row.get('description_match') not in ('未核对', '符合', '部分符合', '不符合'):
            raise ValueError('Invalid description assessment')
        if row.get('separation_quality') not in ('未核对', '可辅助辨听', '明显串音或失真', '无法判断'):
            raise ValueError('Invalid separation assessment')
        for key in ('layer', 'reason'):
            if not isinstance(row.get(key), str) or len(row[key]) > 2000:
                raise ValueError('Invalid feedback text')
        item={k: row[k] for k in ('id','source_sha256','start','end','reaction','description_match','separation_quality','layer','reason')}
        reviews=row.get('evidence_reviews', {}) if value['schema_version']==3 else {}
        if not isinstance(reviews,dict) or len(reviews)>2 or any(
            not re.fullmatch(r'[0-9a-f]{64}',str(k)) or v not in ('未核对','确认','否定','跳过') for k,v in reviews.items()):
            raise ValueError('Invalid evidence reviews')
        item['evidence_reviews']=dict(reviews)
        clean.append(item)
    return dict(schema_version=3, report_id=value['report_id'], feedback=clean)


def preference_pairs(report, feedback):
    feedback = validate_feedback(feedback)
    if feedback['report_id'] != report['report_id']:
        raise ValueError('Feedback belongs to another report')
    fragments = {c['id']: c for t in report['tracks'] for c in t['fragments']}
    rated = {}
    confirmed = {}
    for row in feedback['feedback']:
        c = fragments.get(row['id'])
        if c is None or any(row[k] != c[k] for k in ('source_sha256','start','end')):
            raise ValueError('Feedback source or range mismatch')
        clues={x['id']:x for x in listening_clues(c)}
        if set(row['evidence_reviews'])-set(clues):
            raise ValueError('Evidence changed or belongs to another fragment')
        confirmed[row['id']]={clues[k]['feature'] for k,v in row['evidence_reviews'].items() if v=='确认'}
        if row['reaction'] != '未评价':
            rated[row['id']] = row
    pairs = []
    ids = list(rated)
    for i, a in enumerate(ids):
        for b in ids[i+1:]:
            shared = sorted(confirmed[a] & confirmed[b])
            if shared:
                pairs.append(dict(a=a, b=b, shared_features=shared,
                    different_reactions=rated[a]['reaction'] != rated[b]['reaction'],
                    question='你确认了相同的声音变化，再听两段时感受有什么不同？确认描述不等于确认喜欢的原因。'))
    pairs.sort(key=lambda p: (not p['different_reactions'], -len(p['shared_features']), p['a'], p['b']))
    return dict(rated_count=len(rated), status='待复听验证；不推断稳定偏好', pairs=pairs[:12])


def merge_feedback(report, files):
    rows={}
    for path in files:
        value=validate_feedback(read(path))
        preference_pairs(report,value)  # Reject wrong source/range even for overwritten entries.
        for row in value['feedback']:rows[row['id']]=row
    return dict(schema_version=3,report_id=report['report_id'],feedback=list(rows.values()))


def layer_hypothesis(layers):
    if not layers:
        return '尚无分轨证据，先在混音中核对声音层。'
    names={'drums':'打击乐','bass':'低音','vocals':'人声','other':'其余伴奏'}
    active=[s for s in layers if max(s['before_dbfs'],s['after_dbfs'])>-60]
    if not active:return '分轨能量过低，不作声音层解释。'
    s=max(active,key=lambda s:abs(s['after_dbfs']-s['before_dbfs']))
    delta=s['after_dbfs']-s['before_dbfs']
    direction='更突出' if delta>0 else '有所收回'
    return (f'模型分出的“{names[s["slot"]]}”槽位前后变化较明显（{delta:+.1f} dB），可能听起来{direction}。'
            '请比较原混音和该分轨：这可能是声音层变化，也可能包含串音或分离失真；槽位名称不证明真实声源。')


def window_evidence(models, slug, start, end):
    rows = []
    for engine, model in models.items():
        for track in model['tracks']:
            if track['slug'] != slug:
                continue
            offset = track['source_start']
            for index, window in enumerate(track['semantic']['windows']):
                a, b = offset+window['start_seconds'], offset+window['end_seconds']
                if min(b, end)-max(a, start) > .01 and window.get('status') == 'analyzed':
                    rows.append(dict(engine=engine, start=a, end=b, window_index=index,
                        candidates=window['candidates']))
    return rows


def build(bundle, output, slugs, separate=False):
    import numpy as np
    import soundfile as sf
    bundle, output = Path(bundle).resolve(), Path(output).resolve()
    if not slugs or len(set(slugs))!=len(slugs):raise ValueError('Select distinct tracks')
    # New experiment directory preserves any previous annotations and artifacts.
    output.mkdir(parents=True, exist_ok=False)
    manifest = read(bundle/'manifest.json')
    measured = read(bundle/'measurements.json')
    models = {e: read(bundle/(e+'.json')) for e in ('clap','muq')}
    if not measured.get('completed') or any(not d.get('completed') for d in models.values()):
        raise ValueError('Incomplete input analysis')
    report = dict(schema_version=1, completed=False, selection='Adjacent 10-second RMS / centroid changes; greedy spacing >=30 seconds; heuristic, not semantic event boundaries',
        evidence_files={name: dict(path=str(bundle/name), sha256=digest(bundle/name)) for name in ('manifest.json','measurements.json','clap.json','muq.json')}, tracks=[])
    write(output/'fragments.json', report)
    for slug in slugs:
        if not re.fullmatch('[a-z0-9-]+', slug):
            raise ValueError('Invalid slug')
        original = next(t for t in manifest if t['slug'] == slug)
        if digest(original['path']) != original['sha256']:
            raise ValueError('Original source changed')
        measurements = sorted((t for t in measured['tracks'] if t['slug'] == slug), key=lambda t:t['source_start'])
        windows = [w for t in measurements for w in t['windows']]
        cursor = 0.
        native = []
        for t in measurements:
            if t['source_sha256'] != original['sha256'] or abs(t['source_start']-cursor) > .002:
                raise ValueError('Measurement source/range mismatch')
            path = bundle/f'{slug}-{t["source_start"]:g}-native.wav'
            if digest(path) != t['native']['sha256']:
                raise ValueError('Native audio changed')
            samples, sr = sf.read(path, dtype='float32', always_2d=True)
            if sr != t['native']['sample_rate'] or samples.shape[1] != t['native']['channels'] or not np.isfinite(samples).all():
                raise ValueError('Invalid native audio')
            if native and sr != native[0][1]:
                raise ValueError('Sample rates differ')
            native.append((samples, sr)); cursor += len(samples)/sr
        for model in models.values():
            tracks = sorted((t for t in model['tracks'] if t['slug']==slug),key=lambda t:t['source_start'])
            if len(tracks)!=len(measurements): raise ValueError('Model coverage differs')
            for t,m in zip(tracks,measurements):
                if t['source_sha256'] != original['sha256'] or abs(t['source_start']-m['source_start'])>.002 or abs(t['semantic']['selected_seconds']-m['native']['duration'])>.002:
                    raise ValueError('Model source/range mismatch')
        audio = np.concatenate([a for a,_ in native]); sr = native[0][1]
        gain = min(1., .999/max(float(np.max(np.abs(audio))),1e-12))
        folder = output/slug; folder.mkdir()
        sf.write(folder/'listening.wav', audio*gain, sr, subtype='PCM_16')
        track = dict(slug=slug, name=Path(original['path']).stem, source_sha256=original['sha256'],
            duration=cursor, listening_gain_db=20*math.log10(gain), fragments=[])
        for index, change in enumerate(select_changes(windows)):
            c = dict(change, id=f'{slug}-{index+1}', source_sha256=original['sha256'])
            c['evidence'] = window_evidence(models, slug, c['start'], c['end'])
            c['features'] = sorted({engine+':'+group+':'+row['id'] for e in c['evidence']
                for engine in [e['engine']] for group in ('instruments','timbre','mood')
                for row in e['candidates'].get(group,[])[:1]})
            db = c['rms_delta_db']
            c['observation'] = f'在约 {c["boundary"]:.0f} 秒附近，后窗相对前窗 RMS {db:+.1f} dB，频谱重心为前窗的 {c["centroid_ratio"]:.2f} 倍。'
            if abs(db)>=2:
                c['interpretation'] = ('力度可能更向前、对比更鲜明。' if db>0 else '力度可能收回，给人留出呼吸或悬置的空间。')
            else:
                c['interpretation'] = '力度变化较小，值得关注音色重心或不同声音层的变化。'
            c['uncertainty'] = '这是待复听的解释。能量与频谱变化不能单独证明乐器进入、鼓退出、配器变厚或特定情绪；模型标签来自混音，不是各分轨的识别结果。'
            c['separation'] = dict(status='not_requested')
            if separate:
                deep = folder/c['id']
                python = ROOT/'.venv-deep/Scripts/python.exe'
                subprocess.run([str(python),str(ROOT/'deep_analysis.py'),original['path'],'--start',str(c['start']),
                    '--duration',str(c['end']-c['start']),'--output',str(deep)],check=True)
                subprocess.run([str(python),str(ROOT/'separate_audio.py'),str(deep)],check=True)
                subprocess.run([str(python),str(ROOT/'prepare_listening.py'),str(deep)],check=True)
                r = read(deep/'report.json')
                layers=[]
                for stem in r['separation'].get('stems',[]):
                    p=deep/stem['path']
                    if digest(p)!=stem['sha256']:raise ValueError('Stem changed')
                    x,ssr=sf.read(p,always_2d=True); cut=round((c['boundary']-c['start'])*ssr)
                    def rms(v):return 20*math.log10(max(float(np.sqrt(np.mean(v*v))),1e-12))
                    layers.append(dict(slot=stem['name'],before_dbfs=rms(x[:cut]),after_dbfs=rms(x[cut:])))
                c['separation']=dict(status=r['separation']['status'],quality='未人工核对',layers=layers,
                    player=f'{c["id"]}/player.html',report_sha256=digest(deep/'report.json'))
            c['layer_hypothesis']=layer_hypothesis(c['separation'].get('layers',[]))
            track['fragments'].append(c)
        if digest(original['path']) != original['sha256']:raise ValueError('Source changed during build')
        report['tracks'].append(track)
        write(output/'fragments.json', report)
    report['completed']=True
    report['report_id']=hashlib.sha256(json.dumps(report,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    render(output,report)
    write(output/'fragments.json',report)
    return report


def render(output, report):
    from deep_analysis import render_player
    lines=['# 片段级听感实验','', '变化来自相邻 10 秒窗口；位置为粗定位，不是精确事件边界。解释供复听核对，反馈尚不代表稳定偏好。','']
    links=[]
    for t in report['tracks']:
        folder=output/t['slug']
        player=dict(source=dict(name=t['name'],sha256=t['source_sha256']),range=dict(start=0,end=t['duration'],duration=t['duration']),
            listening=dict(shared_gain_db=t['listening_gain_db'],tracks=dict(original=dict(path='listening.wav'))),
            tonal=dict(chords=[]),separation=dict(stems=[]),structure=dict(segments=[dict(label=c['id'],start=c['start'],end=c['end']) for c in t['fragments']],repeat_candidates=[]))
        render_player(folder,player)
        page=(folder/'player.html').read_text(encoding='utf8')
        page=page.replace('</style>','a{color:#8ed2ff}textarea{font:inherit;padding:8px;box-sizing:border-box}summary{cursor:pointer;padding:12px 0}</style>')
        page=page.replace('<h1>音乐的结构与层次</h1>',f'<h1>{html.escape(t["name"])}</h1><p>听一小段，选一个感受，就可以了。没有标准答案。</p><p><a href="../index.html">换一首歌</a></p>')
        page=page.replace('<p id="source">','<p id="source" hidden>')
        page=page.replace('<p class="warn">','<p class="warn" hidden>')
        page=page.replace('<section><label>试听声部','<section hidden><label>试听声部')
        page=page.replace('<section><h2>变化段落</h2>','<section hidden><h2>变化段落</h2>')
        page=page.replace('</style>','button[aria-pressed="true"]{background:#307a6b;border-color:#8be0c4}details{margin:18px 0}body{max-width:760px}button{cursor:pointer}button:disabled{opacity:.4;cursor:default}</style>')
        page=page.replace('<section><h2>相似片段 A / B 对照</h2>','<section hidden><h2>相似片段 A / B 对照</h2>')
        page=page.replace('<p id="chord">','<p id="chord" hidden>')
        page=page.replace('<section><img src="overview.png" alt="自相似、结构变化和原始声道能量图"></section>','')
        # Hide legacy point markers: this experiment records interval feedback instead.
        page=page.replace('<section><h2>你的标记</h2>','<section hidden><h2>你的标记</h2>')
        view_track=dict(t,fragments=[dict(c,clues=listening_clues(c)) for c in t['fragments']])
        payload=json.dumps(dict(report_id=report['report_id'],track=view_track),ensure_ascii=False).replace('<','\\u003c')
        extra='<section><p id="fragment-progress"></p><div id="fragment-cards"></div><div id="simple-playstatus"></div><button id="previous-fragment">上一段</button><button id="next-fragment">下一段（也可以跳过）</button></section><button id="save-feedback">保存这次记录</button><p id="feedback-status" role="status"></p><details><summary>导出备份</summary><textarea id="feedback-json" aria-label="反馈 JSON" rows="8" style="width:100%" readonly hidden></textarea><a id="feedback-download" hidden>下载反馈</a></details><details><summary>回头比较听过的片段</summary><div id="preference-pairs"></div></details>'
        page=page.replace('</html>',extra+'<script>const fragments='+payload+';</script><script>'+(ROOT/'fragment_controls.js').read_text(encoding='utf8')+'</script></html>')
        (folder/'player.html').write_text(page,encoding='utf8')
        links.append(f'<li><a href="{t["slug"]}/player.html">{html.escape(t["name"])}</a> · {len(t["fragments"])} 个变化候选</li>')
        lines += [f'## {t["name"]}','',f'[打开试听与反馈]({t["slug"]}/player.html)','']
        for c in t['fragments']:
            if c['separation']['status']=='completed':
                deep_page=folder/c['separation']['player']
                deep_html=deep_page.read_text(encoding='utf8')
                if '返回片段反馈' not in deep_html:
                    deep_html=deep_html.replace('<h1>音乐的结构与层次</h1>','<h1>音乐的结构与层次</h1><p><a href="../player.html">返回片段反馈</a></p>')
                deep_html=deep_html.replace('<section><h2>你的标记</h2>','<section hidden><h2>你的标记</h2>')
                if 'a{color:#8ed2ff}' not in deep_html:deep_html=deep_html.replace('</style>','a{color:#8ed2ff}</style>')
                deep_page.write_text(deep_html,encoding='utf8')
            lines += [f'### {c["id"]} · {c["start"]:.0f}–{c["end"]:.0f} 秒','', '**观察**：'+c['observation'],'','**听感假设**：'+c['interpretation'],'','**声音层假设**：'+c.get('layer_hypothesis',layer_hypothesis(c['separation'].get('layers',[]))),'','**尚未确认**：'+c['uncertainty'],'']
            for e in c['evidence']:
                groups=[' / '.join(r['label'] for r in e['candidates'].get(g,[])[:2]) for g in ('instruments','timbre','mood')]
                lines.append(f'- {e["engine"]} {e["start"]:.0f}–{e["end"]:.0f}s 候选：'+'；'.join(groups))
            if c['separation']['status']=='completed':
                lines += ['',f'[原混音／分轨对照]({t["slug"]}/{c["separation"]["player"]})。分轨质量未人工核对；槽位名不证明声音身份。','']
            lines += ['','反馈保存在浏览器草稿或 listening-exports；本静态报告不汇总实际评价。','']
    (output/'report.md').write_text('\n'.join(lines),encoding='utf8')
    (output/'index.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>片段听感实验</title><style>body{font:18px system-ui;max-width:900px;margin:60px auto;padding:24px}li{margin:24px}</style><h1>片段听感实验</h1><p>先听原混音，记录感受，再展开解释及分轨核对。</p><ul>'+''.join(links)+'</ul><p>所有音频与反馈留在本机。模型相似度不是准确率或用户偏好。</p></html>',encoding='utf8')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    b=sub.add_parser('build');b.add_argument('bundle',type=Path);b.add_argument('output',type=Path)
    b.add_argument('--tracks',nargs='+',default=['arcahv','pinnacle']);b.add_argument('--separate',action='store_true')
    r=sub.add_parser('render');r.add_argument('output',type=Path)
    f=sub.add_parser('feedback');f.add_argument('report',type=Path);f.add_argument('feedback',type=Path,nargs='+');f.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.command=='build':build(args.bundle,args.output,args.tracks,args.separate)
    elif args.command=='render':
        report=read(args.output/'fragments.json')
        if not report.get('completed'):raise ValueError('Incomplete report')
        render(args.output,report)
    else:
        report=read(args.report)
        result=preference_pairs(report,merge_feedback(report,args.feedback))
        with args.output.open('x',encoding='utf8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
