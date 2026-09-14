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
