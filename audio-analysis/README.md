# 音频分析工具

项目入口与基本安装见 [根 README](../README.md)，功能和验证边界见 [STATUS](../STATUS.md)。所有命令在本目录执行；输入音频使用你自己的本地路径。

## 可选环境

```powershell
# MuQ（独立 CPU 环境）
./.venv/Scripts/python.exe -m venv .venv-muq
./.venv-muq/Scripts/python.exe -m pip install -r requirements-muq.lock.txt --extra-index-url https://download.pytorch.org/whl/cpu
./.venv/Scripts/python.exe setup_muq.py
# Essentia ONNX
./.venv/Scripts/python.exe -m venv .venv-essentia
./.venv-essentia/Scripts/python.exe -m pip install --only-binary=:all: -r requirements-essentia.lock.txt
./.venv/Scripts/python.exe setup_essentia.py
# 深度分析与 MELODIA
./.venv/Scripts/python.exe -m venv .venv-deep
./.venv-deep/Scripts/python.exe -m pip install -r requirements-deep.lock.txt --extra-index-url https://download.pytorch.org/whl/cpu
./.venv/Scripts/python.exe setup_separation.py
npm.cmd ci --prefix .reference-essentia-js --ignore-scripts --no-audit --no-fund
```

深度环境锁文件包含历史安装时带入的 MuQ 依赖，不表示深度分析默认加载 MuQ。不同模型环境不要混用。

## 分析

```powershell
./.venv/Scripts/python.exe compare_models.py 'D:/Music/song.flac' --engines clap muq essentia
./.venv-essentia/Scripts/python.exe essentia_cli.py 'D:/Music/song.flac' --whole-file
./.venv-deep/Scripts/python.exe deep_cli.py 'D:/Music/song.flac' --whole-file
```

单次最多 600 秒；支持 --start 和 --duration。报告和音轨生成到 results/，不会纳入源码发布。试听标记只代表手动反馈，尚未用于训练偏好模型。

## 检查

基础报告和三模型对照报告优先展示听感导读：整体氛围、声音质感、按原文件时间合并的复听区间，以及尚不能解释的部分。导读仅整理已完成的模型输出，不新增推理，不代表人工听辨或个人偏好。不同模型分开呈现；参数和原始候选保留在后面的技术证据中。时间区间供在本机播放器中定位，不会自动播放。

导读边界测试：`./.venv/Scripts/python.exe -m unittest listening_selftest`。

```powershell
./.venv/Scripts/python.exe selftest.py
./.venv/Scripts/python.exe preview_selftest.py
./.venv/Scripts/python.exe -m unittest deep_selftest comparison_selftest
./.venv/Scripts/python.exe setup_reference.py
./.venv/Scripts/python.exe semantic_selftest.py
./.venv-essentia/Scripts/python.exe essentia_selftest.py
./.venv-deep/Scripts/python.exe separation_selftest.py
./.venv/Scripts/python.exe melody_selftest.py
```

模型测试须先准备对应模型，参考音频测试须先运行 setup_reference.py；合成测试产生的文件留在本机。上述命令是运行说明，本次发布整理未重新执行全部模型测试。

## 片段级听感实验

### 旋律跟踪能力诊断

`melody_analysis.py` 会记录候选覆盖、最长漏检和相邻帧大跳次数；这些都不是准确率。对已完成分轨的深度分析目录，可运行：

```powershell
.venv-deep/Scripts/python.exe melody_analysis.py results/你的深度分析目录 --compare-other
.venv-deep/Scripts/python.exe prepare_listening.py results/你的深度分析目录
```

该路径保持 MELODIA 默认参数，对原混音和校验后的 `other` 槽位各自推理，保存独立 CSV、原生置信值、等幅正弦试听及 `melody-comparison.md/json`。不自动用覆盖更多的分轨结果替换原混音轮廓。两条路径的一致率也不等于准确率；分轨仍可能串音，真实旋律需人工核对。运行会更新该目录的诊断与试听页，不改原音乐。

### 使用片段反馈

使用已有本地参考分析包（`manifest.json`、`measurements.json`、CLAP/MuQ JSON 和原声道解码副本），选择相邻窗口变化并生成试听、分层证据与反馈页。输出必须是新目录，不覆盖旧反馈：

```powershell
.venv-deep/Scripts/python.exe fragment_report.py build results/human-reference-20260914 results/fragment-experiment --tracks arcahv pinnacle --separate
.venv/Scripts/python.exe serve_audio.py results/fragment-experiment --port 8877
```

打开 `http://127.0.0.1:8877/index.html`。每首最多 4 个相隔至少 30 秒的变化候选，按相邻 10 秒窗口的能量及频谱重心变化选择，并非精确事件检测。`--separate` 用已有隔离环境、锁定 HTDemucs 权重离线分轨；不指定时仍可分析混音证据。各槽位前后能量和模型候选分别显示，不把混音标签强加给分轨。试听副本和分析音频分开，分轨使用共同增益；质量须通过原混音对照确认。

页面先听后展开解释。反馈分别记录喜欢／无感／不喜欢、声音层、原因、描述吻合度与分轨质量；未评价不会算作无感。草稿保留在当前浏览器；“保存片段反馈”通过同源回环接口写入 `listening-exports`，也提供 JSON 下载及复制。不会自动把用户反馈写进源码或生成固定偏好结论。

反馈与来源指纹、片段范围、报告 ID 绑定。生成后续复听对照：

```powershell
.venv/Scripts/python.exe fragment_report.py feedback results/fragment-experiment/fragments.json results/fragment-experiment/listening-exports/你的反馈.json --output results/fragment-experiment/preference-questions.json
.venv/Scripts/python.exe fragment_selftest.py
```

对照优先列出共同模型候选、但个人反应不同的片段。这只是复听问题；候选重合并非听感相同，更不证明偏好原因。CLI 输出也必须使用新文件名。

`feedback` 命令可以连续传入两首歌的多个反馈 JSON，生成跨曲目对照；同一片段重复出现时，以命令中后面的文件为准。来源或范围不匹配的记录会被拒绝。
