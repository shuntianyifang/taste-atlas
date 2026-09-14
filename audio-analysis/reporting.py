"""Human-readable Chinese report and per-window semantic export."""
import csv
from pathlib import Path

GROUPS = {'instruments': '乐器候选', 'timbre': '音色质感候选', 'mood': '情绪氛围候选',
          'vocals': '人声情况候选', 'context': '编曲/风格候选'}


def timestamp(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    return f'{minutes:02d}:{seconds:02d}'


def write_report(result, output):
    segment = result['segment']
    start, duration = segment['start_seconds'], segment['duration_seconds']
    total = result['source'].get('length')
    full = total is not None and start == 0 and abs(duration - total) < .5
    scope = '全曲' if full else '选定片段（不是全曲结论）'
    source_name = str(result['source']['file']).replace('\n', ' ').replace('\r', ' ')
    lines = ['# 音频分析报告', '', f'文件：{source_name}', '',
             f'范围：{scope}，{timestamp(start)}–{timestamp(start + duration)}，实际 {duration:.2f} 秒。', '',
             '## 实测声学特征', '',
             f'- 估计节拍：{result["estimated_bpm"] if result["estimated_bpm"] is not None else "证据不足"} BPM（可能半速/倍速）。',
             f'- RMS：{result["rms_dbfs"]:.2f} dBFS。',
             '- 以下声学特征来自 22050 Hz 单声道；不能据此直接确定乐器和情绪。']
    timbre = result.get('acoustic_timbre', {})
    if timbre.get('status') == 'measured':
        lines += [f'- 频谱重心中位数：{timbre["median_spectral_centroid_hz"]:.1f} Hz。',
                  f'- 85% 频谱滚降点中位数：{timbre["median_rolloff_85_hz"]:.1f} Hz。',
                  f'- 频谱平坦度中位数：{timbre["median_spectral_flatness"]:.5f}。',
                  f'- 低于 250 Hz 的能量占比：{timbre["energy_below_250_hz_ratio"]:.1%}。',
                  f'- 高于 4000 Hz 的能量占比：{timbre["energy_above_4000_hz_ratio"]:.1%}。',
                  f'- 活跃帧 RMS P95/P10 跨度：{timbre["active_rms_p95_p10_range_db"]:.2f} dB（不是母带 LRA）。']
        lines += [f'- {text}。' for text in timbre['descriptors']]
    semantic = result.get('semantic', {})
    lines += ['', '## 模型推测：需要听辨确认', '',
              '模型比较真实音频和固定文字候选的相似度，不读取文件名来猜风格。相似度不是识别概率，情绪也不代表你本人的感受。', '']
    if semantic.get('status') != 'analyzed':
        lines += [f'语义分析状态：{semantic.get("status", "not_run")}。', semantic.get('reason', '音频过短或信号不足。')]
    else:
        lines += [f'模型：CLAP，固定版本 `{semantic["revision"]}`；48 kHz 单声道、10 秒窗口，本地 CPU 推理。',
                  f'有效分析 {semantic["analyzed_seconds"]:.2f} / {semantic["selected_seconds"]:.2f} 秒。', '']
        for key, label in GROUPS.items():
            group = semantic['overall_candidates'][key]
            lines += [f'### {label}', '', '| 候选 | 余弦相似度 |', '|---|---:|']
            for item in group['candidates'][:4]:
                lines.append(f'| {item["label"]} | {item["cosine_similarity"]:.3f} |')
            flag = group['assessment']
            if flag == 'weak_match':
                lines += ['', '整体匹配偏弱，不能可靠判断。']
            elif flag == 'close_candidates':
                lines += ['', '前两项分数接近，保留多个解释。']
            lines += ['']
        lines += ['## 随时间变化的候选', '', '| 原音频时段 | 乐器前二 | 情绪前二 | 音色前二 |', '|---|---|---|---|']
        for window in semantic['windows']:
            interval = f'{timestamp(window["start_seconds"])}–{timestamp(window["end_seconds"])}'
            if window['status'] != 'analyzed':
                lines.append(f'| {interval} | 信号不足 | 不判断 | 不判断 |')
                continue
            labels = ['、'.join(item['label'] for item in window['candidates'][key][:2]) for key in ('instruments', 'mood', 'timbre')]
            lines.append(f'| {interval} | {labels[0]} | {labels[1]} | {labels[2]} |')
        lines += ['', '## 分析边界', ''] + [f'- {item}' for item in semantic['limitations']]
    lines += ['', '本工具不上传音频，不修改原文件；报告将实测特征与模型候选分开，不能替代逐轨人工听辨。', '']
    (output / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    with (output / 'semantic_timeline.csv').open('w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.writer(handle)
        writer.writerow(['start_seconds', 'end_seconds', 'status', 'group', 'rank', 'label', 'cosine_similarity'])
        for window in semantic.get('windows', []):
            for group, candidates in window.get('candidates', {}).items():
                for rank, item in enumerate(candidates, 1):
                    writer.writerow([window['start_seconds'], window['end_seconds'], window['status'], group, rank,
                                     item['label'], item['cosine_similarity']])
