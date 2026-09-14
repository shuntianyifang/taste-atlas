"""Compare source/time coverage, never compare incompatible score scales."""
import json
from essentia_reporting import describe


def validate(data):
    if not data or any(not d.get('completed') for d in data.values()):
        raise ValueError('Incomplete model run')
    baseline = next(iter(data.values()))
    for model in data.values():
        if len(model['tracks']) != len(baseline['tracks']):
            raise ValueError('Track count mismatch')
        for a, b in zip(baseline['tracks'], model['tracks']):
            if a['source_sha256'] != b['source_sha256']:
                raise ValueError('Source mismatch')
            sa, sb = a['semantic'], b['semantic']
            if abs(sa['selected_seconds'] - sb['selected_seconds']) > .001 or len(sa['windows']) != len(sb['windows']):
                raise ValueError('Coverage mismatch')
            for x, y in zip(sa['windows'], sb['windows']):
                if any(abs(x[k] - y[k]) > .001 for k in ('start_seconds', 'end_seconds')):
                    raise ValueError('Window mismatch')
    if 'clap' in data and 'muq' in data and data['clap'].get('label_sha256') != data['muq'].get('label_sha256'):
        raise ValueError('CLAP/MuQ label mismatch')


def candidates(result, group, engine):
    if engine == 'essentia':
        return describe(result['overall'].get({'instruments': 'instrument', 'mood': 'moodtheme'}.get(group, '')))
    rows = result['overall_candidates'].get(group, {}).get('candidates', [])[:3]
    return '、'.join(f'{r["label"]} ({r["cosine_similarity"]:.3f})' for r in rows) or '无有效预测'


def report(directory, engines):
    data = {e: json.loads((directory / f'{e}.json').read_text(encoding='utf-8')) for e in engines}
    validate(data)
    lines = ['# 音乐模型实测对照', '',
        '原文件与分析时段经过指纹和时间检查。各模型使用自身采样率与原生窗口；Essentia 原生重叠窗口按交集时长汇总到 10 秒区间。', '',
        'CLAP/MuQ 输出文字相似度，Essentia 输出固定标签分类值与 DEAM 回归值。分数不可跨模型比较；没有人工标注准确率，也不按模型数量投票。', '',
        'Essentia 的 moodtheme 包含情绪与用途标签，不等同于纯情绪词表；无独立音色、人声或流派任务的栏目不填充推测结果。', '',
        '25 个帧的频谱前处理已与官方 Essentia.js 0.1.3 核对；完整 TensorFlow 推理流水线的数值等价验证仍未完成。', '',
        '| 模型 | 初始化秒数 |', '|---|---|']
    lines += [f'| {e} | {d["initialization_seconds"]:.2f} |' for e, d in data.items()]
    first = next(iter(data.values()))
    for i, track in enumerate(first['tracks']):
        lines += ['', f'## {track["file"]}', '', f'分析时长：{track["semantic"]["selected_seconds"]:.3f} 秒。', '',
                  '| 模型 | 乐器前三 | 情绪或主题前三 | 解码与推理秒数 |', '|---|---|---|---|']
        for e, d in data.items():
            t = d['tracks'][i]
            lines.append(f'| {e} | {candidates(t["semantic"], "instruments", e)} | {candidates(t["semantic"], "mood", e)} | {t["elapsed_seconds"]:.2f} |')
        if 'essentia' in data:
            t = data['essentia']['tracks'][i]
            d = t['semantic']['overall']['deam']
            lines += ['', f'DEAM 均值：愉悦度 {d["valence"]:.2f}，激活程度 {d["arousal"]:.2f}。' if d else 'DEAM 无有效预测。', '',
                      f'![情绪曲线]({t["artifact_directory"]}/emotion.png)', '',
                      f'[Essentia 完整报告与时间轴说明]({t["artifact_directory"]}/report.md)', '',
                      '曲线为原生窗口预测，未裁剪越界值；训练标签标度 1–9，不代表听众实际感受。']
        lines += ['', '| 时段 | ' + ' | '.join(engines) + ' |', '|---|' + '---|' * len(engines)]
        for j, window in enumerate(track['semantic']['windows']):
            values = []
            for e, d in data.items():
                w = d['tracks'][i]['semantic']['windows'][j]
                if e == 'essentia':
                    values.append(describe(w.get('moodtheme'), 1))
                else:
                    rows = w.get('candidates', {}).get('mood', [])
                    values.append(rows[0]['label'] if rows else '不判断')
            lines.append(f'| {window["start_seconds"]:.2f}–{window["end_seconds"]:.2f} | ' + ' | '.join(values) + ' |')
    lines += ['', '## 小号参考检查', '']
    for e, d in data.items():
        check = d.get('reference_check', {})
        text = describe(check.get('instrument_scores')) if e == 'essentia' else '、'.join(x['label'] for x in check.get('instrument_candidates', [])[:3])
        lines.append(f'- {e}：{text or "参考检查未执行"}。')
    lines += ['', '小号样本仅用于合理性检查；其排名失败须保留，不能调整阈值让测试表面通过。', '',
              '同义标签映射只用于解读：piano↔钢琴，strings↔弦乐，synthesizer↔合成器，epic↔史诗，dream↔梦幻，calm↔平静。',
              'brass/trumpet、sad/melancholic 等粒度不同的标签不合并计分；不计算跨模型统一置信度。']
    (directory / 'comparison.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
