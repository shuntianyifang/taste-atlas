"""Evidence-bound listening guide; no new inference or preference claims."""


def stamp(value):
    return f'{int(value)//60:02d}:{value%60:05.2f}'


def listening_summary(semantic, engine='CLAP', acoustic=None):
    lines = ['### 听感概览', '',
             '以下是已有模型结果支持的听感线索，尚未经人工复听确认；描述音乐候选特征，不推断你是否喜欢。', '']
    groups = semantic.get('overall_candidates', {})
    for key, title, question in (
        ('mood', '整体氛围', '这些氛围是否符合你的实际听感？'),
        ('timbre', '声音质感', '注意声音的延续、颗粒和空间感。')):
        group = groups.get(key, {})
        rows = group.get('candidates', [])
        if not rows or group.get('assessment') == 'weak_match':
            lines += [f'- **{title}**：证据不足，暂不描述。']
            continue
        labels = '；'.join(r['label'] for r in rows[:3])
        note = '候选接近，不能确定主导感觉。' if group.get('assessment') == 'close_candidates' else ''
        lines += [f'- **{title}**：{engine} 的候选提示“{labels}”。{note}{question}']
    lines += ['', '### 时间变化与复听依据', '',
              f'按原文件时间复听下列区间；相邻且情绪与音色首选相同的有效窗口合并。边界表示 {engine} 标签变化，不等于曲式、高潮或实际听感突变。', '',
              '| 原文件时间 | 氛围线索 | 质感线索 |', '|---|---|---|']
    runs = []
    for window in semantic.get('windows', []):
        valid = window.get('status') == 'analyzed'
        candidates = window.get('candidates', {}) if valid else {}
        pair = tuple((candidates.get(k) or [{}])[0].get('label', '证据不足') for k in ('mood', 'timbre'))
        start, end = window['start_seconds'], window['end_seconds']
        if valid and runs and runs[-1][3] and runs[-1][2] == pair and abs(runs[-1][1]-start) < .001:
            runs[-1][1] = end
        else:
            runs.append([start, end, pair, valid])
    for start, end, pair, _ in runs:
        lines.append(f'| {stamp(start)}–{stamp(end)} | {pair[0]} | {pair[1]} |')
    if not runs:
        lines += ['| — | 无有效时间证据 | 无有效时间证据 |']
    lines += ['', '复听时重点比较相邻区间：氛围是否真的改变，还是只有模型用词改变？音色发生变化时，能否听到新的声音进入或原有声音退出？', '',
              '### 尚不能解释的部分', '',
              '- 当前证据不足以说明旋律如何制造紧张与释放、确切的演奏方式或你的情感来源；不据标签编写这些原因。']
    if acoustic and acoustic.get('status') == 'measured':
        lines += ['- 声学测量补充：' + '；'.join(acoustic.get('descriptors', [])) + '。',
                  '- 频谱描述与模型质感词来自不同依据，可能不一致。例如“偏暗”与“明亮”并存时，需要复听确认所指声部，不能直接合成统一结论。']
    lines += [f'- 证据来源：{engine} 的 overall_candidates 与 windows；具体分数、其他候选及测量值见后面的技术证据。', '']
    return lines
