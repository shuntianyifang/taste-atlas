"""Compare the installed CLAP and MuQ on identical full recordings, offline."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import uuid

ROOT = Path(__file__).resolve().parent
GROUPS = {'instruments': '乐器', 'timbre': '音色', 'mood': '情绪', 'vocals': '人声', 'context': '编曲风格'}


def report(directory, engines=('clap', 'muq')):
    if tuple(engines) != ('clap', 'muq'):
        from multi_model_report import report as multi_report
        return multi_report(directory, engines)
    clap, muq = [json.loads((directory / f'{name}.json').read_text(encoding='utf-8')) for name in ('clap', 'muq')]
    if not clap.get('completed') or not muq.get('completed'):
        raise ValueError('Incomplete run; comparison cannot be marked complete')
    if len(clap['tracks']) != len(muq['tracks']):
        raise ValueError('Track count mismatch')
    if clap.get('label_sha256') != muq.get('label_sha256'):
        raise ValueError('Label bank mismatch')
    lines = ['# CLAP 与 MuQ-MuLan 实测对照', '',
        '两模型在本机 CPU 运行，推理期间阻断网络连接；使用相同原文件、全曲范围、10 秒窗口和 labels.json 英文描述。', '',
        'CLAP：48 kHz，ONNX 音频 FP32 / 文本 INT8；MuQ-MuLan：24 kHz，PyTorch FP32。各自遵循模型输入采样率。', '',
        '相似度仅用于各模型内部排序，不能跨模型比较大小或推断准确率。排名一致率也不是准确率。没有人工情绪真值。', '',
        '短尾片段：CLAP repeatpad，MuQ repeat-to-length；低于 2 秒或 RMS 低于 -65 dBFS 不判断。整曲按原始有效时长加权。', '',
        f'初始化（含完整性校验及可能的文本缓存生成）：CLAP {clap["initialization_seconds"]:.1f} 秒；MuQ {muq["initialization_seconds"]:.1f} 秒。', '']
    for a, b in zip(clap['tracks'], muq['tracks']):
        if a['source_sha256'] != b['source_sha256']:
            raise ValueError('Source mismatch')
        sa, sb = a['semantic'], b['semantic']
        if abs(sa['selected_seconds'] - sb['selected_seconds']) > .01 or len(sa['windows']) != len(sb['windows']):
            raise ValueError('Window mismatch')
        for x, y in zip(sa['windows'], sb['windows']):
            if abs(x['start_seconds'] - y['start_seconds']) > .001 or abs(x['end_seconds'] - y['end_seconds']) > .001:
                raise ValueError('Window boundary mismatch')
        lines += [f'## {a["file"]}', '',
            f'全曲 {sa["selected_seconds"]:.2f} 秒，{len(sa["windows"])} 个窗口。解码与分析耗时：CLAP {a["elapsed_seconds"]:.1f} 秒；MuQ {b["elapsed_seconds"]:.1f} 秒。', '',
            '| 维度 | CLAP 前三候选 | MuQ-MuLan 前三候选 | 窗口首选一致率 |', '|---|---|---|---|']
        for group, title in GROUPS.items():
            ca, cb = [s['overall_candidates'].get(group, {}).get('candidates', [])[:3] for s in (sa, sb)]
            def display(items):
                return '、'.join(f'{i["label"]}（{i["cosine_similarity"]:.3f}）' for i in items) or '无有效信号，不判断'
            pairs = [(x, y) for x, y in zip(sa['windows'], sb['windows']) if x['status'] == y['status'] == 'analyzed']
            equal = sum(x['candidates'][group][0]['id'] == y['candidates'][group][0]['id'] for x, y in pairs)
            agreement = f'{equal}/{len(pairs)}' if pairs else '无有效窗口'
            lines.append(f'| {title} | {display(ca)} | {display(cb)} | {agreement} |')
        lines += ['', '### 分段情绪首选', '', '| 时段（秒） | CLAP | MuQ-MuLan |', '|---|---|---|']
        for x, y in zip(sa['windows'], sb['windows']):
            def mood(w):
                return w['candidates']['mood'][0]['label'] if w['status'] == 'analyzed' else '不判断'
            lines.append(f'| {x["start_seconds"]:.0f}–{x["end_seconds"]:.2f} | {mood(x)} | {mood(y)} |')
        lines.append('')
    lines += ['## 验证与解释边界', '']
    for data in (clap, muq):
        check = data.get('reference_check', {})
        top = check.get('instrument_candidates', [{}])[0].get('label', '未运行')
        lines.append(f'- {data["engine"]}：小号参考第一候选为“{top}”；验证详情见对应 JSON。')
    lines += ['', '小号样本仅用于单样本合理性检查，不能推出复杂混音的乐器准确率。两首真实曲目的结果需要结合人工复听判断；保留模型分歧，不自动宣布胜者。',
              '', 'MuQ 权重采用 CC-BY-NC 4.0；本轮用于本机个人分析。来源和固定提交见 models/muq-manifest.json。']
    (directory / 'comparison.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='*', type=Path)
    parser.add_argument('--report-only', type=Path)
    parser.add_argument('--engines', nargs='+', choices=['clap', 'muq', 'essentia'], default=['clap', 'muq'])
    args = parser.parse_args()
    if len(set(args.engines)) != len(args.engines):
        parser.error('Do not repeat engines')
    if args.report_only:
        report(args.report_only, args.engines)
        return
    if not args.files:
        parser.error('Provide at least one local audio file')
    sources = [str(p.resolve(strict=True)) for p in args.files]
    out = ROOT / 'results' / ('comparison-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    out.mkdir(parents=True)
    (out / 'labels.json').write_bytes((ROOT / 'labels.json').read_bytes())
    for engine in args.engines:
        env = {'clap': '.venv', 'muq': '.venv-muq', 'essentia': '.venv-essentia'}[engine]
        subprocess.run([str(ROOT / env / 'Scripts/python.exe'), str(ROOT / 'compare_worker.py'),
            '--engine', engine, '--output', str(out / f'{engine}.json'), *sources], check=True)
    report(out, args.engines)
    print(out / 'comparison.md', flush=True)


if __name__ == '__main__':
    main()
