# Taste Atlas · 知趣

本地音乐分析与试听工具。提供音频特征、三模型语义候选、四声部分离、旋律／和声候选和可复听的时间轴报告。图片分析及个人审美学习仍在规划中。

详见 [当前状态](STATUS.md)、[源码发布说明](docs/SOURCE_RELEASE.md)和 [第三方说明](audio-analysis/THIRD_PARTY.md)。

## 目录

```text
audio-analysis/    源码、测试、锁文件、模型准备脚本
tools/             源码边界检查与打包
docs/              发布说明
SOURCE_FILES.json  允许发布的文件清单
```

本机另保留 tmp/ 素材，以及 audio-analysis/ 中的 models/、results/、selftest/、.venv*、.cache 等目录；它们不在源码发布清单中。

## 基础安装与运行（Windows PowerShell）

需要 Python 3.12；MELODIA 扩展需要 Node.js（历史验证版本 22.20.0）。

```powershell
cd audio-analysis
py -3.12 -m venv .venv
./.venv/Scripts/python.exe -m pip install --only-binary=:all: -r requirements.lock.txt
./.venv/Scripts/python.exe setup_models.py
./.venv/Scripts/python.exe analyze.py 'D:/Music/song.flac' --whole-file --semantic on
./.venv/Scripts/python.exe serve_audio.py results --port 8878
```

安装阶段下载依赖和模型；推理使用本地文件。音乐不会被上述分析入口上传。独立扩展的安装命令见 [工具说明](audio-analysis/README.md)。复制环境仍依赖本机基础 Python，不随源码分发。

## 源码检查与打包

```powershell
python tools/source_release.py --check
python tools/source_release.py --output dist/taste-atlas-source.zip
```

打包不依赖 Git，不包含音乐、图片、模型、环境、生成结果或历史本机记录。默认不覆盖已有 ZIP。新增源码需要更新清单，并运行 `python tools/source_release.py --write-gitignore` 同步 Git 规则。

## 许可证

Copyright (C) 2026 shuntianyifang。项目原创源码与配套原创文档采用 **AGPL-3.0-only**（GNU Affero General Public License version 3 only），完整条款见 [LICENSE](LICENSE)。本程序不提供任何担保，详见许可证。

第三方组件、模型、音乐与图片不因此重新授权，遵循各自条款；MuQ 与 Essentia 模型仍有非商业限制，详见第三方说明。尚未完成干净机器安装验收，详见 STATUS.md。

源码仓库：https://github.com/shuntianyifang/taste-atlas
