"""Chinese reports and unmodified DEAM time series."""
import csv
import json
from pathlib import Path
import numpy as np

ZH = dict(zip(
    'accordion acousticbassguitar acousticguitar bass beat bell bongo brass cello clarinet classicalguitar computer doublebass drummachine drums electricguitar electricpiano flute guitar harmonica harp horn keyboard oboe orchestra organ pad percussion piano pipeorgan rhodes sampler saxophone strings synthesizer trombone trumpet viola violin voice'.split(),
    '手风琴 原声低音吉他 原声吉他 低音线 节拍 铃声 邦戈鼓 铜管 大提琴 单簧管 古典吉他 电脑制作 低音提琴 鼓机 鼓 电吉他 电钢琴 长笛 吉他 口琴 竖琴 圆号 键盘 双簧管 管弦乐 风琴 铺底音色 打击乐 钢琴 管风琴 罗德电钢琴 采样器 萨克斯 弦乐 合成器 长号 小号 中提琴 小提琴 人声'.split()))
ZH.update(dict(zip(
    'action adventure advertising background ballad calm children christmas commercial cool corporate dark deep documentary drama dramatic dream emotional energetic epic fast film fun funny game groovy happy heavy holiday hopeful inspiring love meditative melancholic melodic motivational movie nature party positive powerful relaxing retro romantic sad sexy slow soft soundscape space sport summer trailer travel upbeat uplifting'.split(),
    '动作 冒险 广告 背景 抒情曲 平静 儿童 圣诞 商业 酷感 企业 暗沉 深沉 纪录片 戏剧 戏剧性 梦幻 情感丰富 活跃 史诗 快速 影视 有趣 滑稽 游戏 律动感 快乐 厚重 假日 希望 鼓舞 爱意 冥想 忧郁 旋律性 激励 电影 自然 聚会 积极 强烈 放松 复古 浪漫 忧伤 性感 缓慢 柔和 声景 太空 运动 夏日 预告片 旅行 轻快 振奋'.split())))


def top(scores, limit=5):
    return sorted((scores or {}).items(), key=lambda x: (-x[1], x[0]))[:limit]


def describe(scores, limit=3):
    return '、'.join(f'{ZH.get(k, k)} [{k}] ({v:.3f})' for k, v in top(scores, limit)) or '无有效预测'


def write_track(track, directory):
    directory.mkdir(parents=True, exist_ok=True)
    result = track['semantic']
    (directory / 'report.json').write_text(json.dumps(track, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# Essentia 音乐分析', '', f'文件：{track["file"]}', '',
             f'分析范围：{result["source_start"]:.2f}–{result["source_start"] + result["selected_seconds"]:.2f} 秒；耗时 {track["elapsed_seconds"]:.2f} 秒。', '',
             '## 整体候选', '', f'- 乐器：{describe(result["overall"]["instrument"], 5)}',
             f'- 情绪与主题：{describe(result["overall"]["moodtheme"], 5)}', '']
    d = result['overall']['deam']
    lines += [f'整体 DEAM：愉悦度 {d["valence"]:.2f}，激活程度 {d["arousal"]:.2f}。' if d else 'DEAM：无有效预测。', '',
              '![DEAM 情绪曲线](emotion.png)', '',
              '训练标签标度为 1–9；点位于实际音频覆盖窗口的中点，原始越界值不裁剪。曲线描述音乐预测特征，不代表听众感受。', '',
              '## 10 秒展示区间', '', '| 时段 | 乐器前三 | 情绪与主题前三 | 愉悦度 / 激活程度 |', '|---|---|---|---|']
    for w in result['windows']:
        d = w.get('deam')
        values = f'{d["valence"]:.2f} / {d["arousal"]:.2f}' if d else '无有效预测'
        lines.append(f'| {w["start_seconds"]:.2f}–{w["end_seconds"]:.2f} | {describe(w.get("instrument"))} | {describe(w.get("moodtheme"))} | {values} |')
    lines += ['', '## 解释边界', ''] + [f'- {s}' for s in result['limitations']]
    (directory / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    with (directory / 'timeline.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['resolution', 'start_seconds', 'end_seconds', 'status', 'group', 'label', 'value', 'padded_frames', 'out_of_training_range'])
        groups = [('native_effnet', result['native_windows']['effnet']), ('native_musicnn', result['native_windows']['musicnn']), ('display_10s', result['windows'])]
        for resolution, windows in groups:
            for w in windows:
                wrote = False
                for group in ('instrument', 'moodtheme', 'deam'):
                    for label, value in (w.get(group) or {}).items():
                        writer.writerow([resolution, w['start_seconds'], w['end_seconds'], w['status'], group, label, value,
                                         w.get('padded_frames', ''), group == 'deam' and not 1 <= value <= 9])
                        wrote = True
                if not wrote:
                    writer.writerow([resolution, w['start_seconds'], w['end_seconds'], w['status'], '', '', '', w.get('padded_frames', ''), ''])
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    native = result['native_windows']['musicnn']
    times = [(w['start_seconds'] + w['end_seconds']) / 2 for w in native]
    fig, ax = plt.subplots(figsize=(11, 4.5), constrained_layout=True)
    ax.axhspan(1, 9, color='#e8edf2', alpha=.6, label='训练标签标度 1–9')
    for key, label, color in [('valence', '愉悦度', '#287b8e'), ('arousal', '激活程度', '#bd644b')]:
        values = np.array([w.get('deam', {}).get(key, np.nan) for w in native])
        ax.plot(times, values, label=label, color=color)
        outside = (values < 1) | (values > 9)
        ax.scatter(np.asarray(times)[outside], values[outside], marker='x', color='red', label=f'{label}越界' if outside.any() else None)
    ax.set(xlabel='原文件时间（秒）', ylabel='模型回归值', title=track['file'])
    ax.set_xlim(result['source_start'], result['source_start'] + result['selected_seconds'])
    ax.legend(loc='best'); ax.grid(alpha=.2)
    fig.savefig(directory / 'emotion.png', dpi=140)
    plt.close(fig)
