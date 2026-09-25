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

页面每段最多提出两条基于能量或频谱变化的听感问题，提供前后试听及确认／否定／跳过；测量只用于提出问题，不能代替人的判断。模型标签、分轨与旧版描述核对折叠到分析依据中。声音印象和个人反应独立记录；旋律跟踪核对不参与偏好推断。

对照只使用两个片段中均被逐条确认的共同声音变化，优先显示个人反应不同的片段。确认变化也不证明偏好原因；未确认、否定或跳过的线索不会参与。反馈导出使用 schema 3，同时接受旧 schema 2；旧喜好及描述核对保留，但不自动转为逐条确认。线索 ID 绑定来源、时段、描述和测量依据，内容变化后须重新核对。CLI 输出仍必须使用新文件名。

更新已有实验的页面（保留报告 ID、浏览器草稿键和已有导出，不重新推理）：

```powershell
.venv-deep/Scripts/python.exe fragment_report.py render results/fragment-experiment
```

`feedback` 命令可以连续传入两首歌的多个反馈 JSON，生成跨曲目对照；同一片段重复出现时，以命令中后面的文件为准。来源或范围不匹配的记录会被拒绝。

### 上下文听感报告

`context_report.py` 将已经整理好的发展解释、连续试听和证据打包成可复用的本地报告。它不会自动写音乐赏析，也不从“认可解释”推断偏好原因。页面先呈现整体解释及连续播放，时间路线、测量依据和不确定性默认折叠。反馈为“有／部分有／没有”，与歌曲喜好、模型准确度分开保存。

```powershell
.venv-deep/Scripts/python.exe context_report.py results/my-analysis/context-spec.json --output results/my-context-report
.venv/Scripts/python.exe serve_audio.py results/my-context-report --port 8880
.venv-deep/Scripts/python.exe context_selftest.py
```

可在 `--output` 前传入多份规格，生成共用入口；输出必须是新目录。规格内路径相对规格文件解析，也可为本机绝对路径。必填字段：

| 字段 | 内容 |
|---|---|
| `slug`、`title` | 小写字母数字连字符标识、展示名称 |
| `source`、`source_sha256` | 原音乐路径及 SHA-256，仅核验，不改写或复制原音乐 |
| `audio`、`audio_sha256` | 连续上下文试听副本及 SHA-256；WAV PCM16，时长须符合范围 |
| `listening_range`、`liked_range` | 原曲秒数 `[起点,终点]`；喜欢范围须位于上下文内，上下文最多600秒 |
| `gain_db` | 制作试听副本时实际使用的共同增益 |
| `explanation` | 连贯解释的段落字符串列表；须明确候选性质 |
| `evidence` | `[{"path":"development-evidence.json","sha256":"文件的64位摘要"}]` |
| `timeline` | `[{"start":120,"end":140,"text":"前文怎样展开","evidence":[0]}]`；索引对应证据列表 |
| `basis_note`、`limitations` | 依据说明字符串、不确定性字符串列表 |
| `history`（可选） | 之前的对话反馈 JSON 路径 |

历史反馈须含 `provenance: "direct_user_conversation"`、相同来源摘要及两个范围、`answer_verbatim: "有"`（也可部分有或没有）。历史仅作为旧记录展示，不预填新反馈。打包器验证文件身份、格式与范围，但不能证明作者的解释正确，也不能独立证明试听副本确实由声明的原文件截取；制作者仍须保留解码／截取证据。

内容、时间或证据改变会产生新的报告 ID，旧草稿不自动转移。本机接口 `/__context_feedback` 仅接受同源回环请求，按服务根目录 `context-index.json` 核对报告身份，反馈写入 `listening-exports/context-feedback-*.json`。保存失败仍可下载或复制备份。不要把 QA 目录的记录用于偏好分析。生成数据和规格保留本机，不纳入源码发布。
