# 第三方模型与参考音频

此文件记录第三方来源及许可。项目原创代码按根目录 LICENSE 使用 AGPL-3.0-only；该授权不覆盖或重新授权第三方组件、模型及用户素材。

- 基础模型：[LAION CLAP HTSAT unfused](https://huggingface.co/laion/clap-htsat-unfused)，模型卡标注 Apache-2.0。
- ONNX 转换：[Xenova/clap-htsat-unfused](https://huggingface.co/Xenova/clap-htsat-unfused)，固定提交 `c28f2883575e590e04d3146ff0713c2448d691ba`。保留原始 README、配置和 SHA-256 manifest 于 models/clap-htsat-unfused/。
- Transformers（Hugging Face，Apache-2.0）提供 tokenizer 和 NumPy 音频处理函数。`semantic.py` 的前处理使用其 `audio_utils`，按 4.57.6 CLAP 非 fusion 路径的 Slaney log-mel / repeatpad 参数调用，未复制或改写已安装库。源码：[feature_extraction_clap.py](https://github.com/huggingface/transformers/blob/v4.57.6/src/transformers/models/clap/feature_extraction_clap.py)。PyTorch 仅为上游通用提取器的依赖，本工具使用 NumPy + ONNX，不安装 PyTorch。
- 小号验收片段：Mihai Sorohan 的 “Jazz Trumpet Loops Pack in F 90 bpm”，[原始 Freesound 页面](https://freesound.org/s/77711/)，[CC-BY 3.0](https://creativecommons.org/licenses/by/3.0/)。下载自 librosa 官方示例集合，原始署名保存在 selftest/reference/sorohanro_-_solo-trumpet-06.txt；SHA-256 对照安装的 librosa 0.11.0 registry。
- NumPy、librosa、ONNX Runtime、FFmpeg 等依赖原有许可保留在虚拟环境各自发行包内。

用户提供的音乐保留原文件，没有复制到源代码仓库或上传外部服务；分析结果不包含音频再分发。

## Essentia ONNX 扩展

- 五个模型来自 [UPF/MTG 官方模型目录](https://essentia.upf.edu/models.html)，采用 CC-BY-NC-SA 4.0；完整原始许可保留于 `models/essentia/MODEL-LICENSE.txt`，不等同于对本工具原创代码新增许可。
- 模型版本、官方下载 URL、首次下载后计算的 SHA-256、大小均记录于 `models/essentia/manifest.json`。该摘要不是官方数字签名，不冒称官方发布的校验值。
- 算法参数参考 [Essentia 源码](https://github.com/MTG/essentia/tree/66a890f285d0e1988155c12d17a2068e406cdd90)，只读参考副本及其 AGPL 许可保留在 `models/essentia/reference/`。Python 前处理调用 NumPy/librosa 的标准数学运算。
- 官方 `essentia.js==0.1.3`（AGPL-3.0）安装于 `.reference-essentia-js`，含 npm 锁文件与上游许可；用于前处理参考校验，也作为 MELODIA / EqualLoudness 主旋律分析的运行依赖；ONNX 标签推理不依赖此 WASM。
- 单帧数值核对不等同于全部流式帧调度、重采样与 TensorFlow 推理流程的等价验证。

## MuQ 来源与许可

- [腾讯 AI Lab MuQ](https://github.com/tencent-ailab/MuQ)：Python 包 `muq==0.1.0`，代码 MIT；MuQ 与 MuQ-MuLan 权重为 **CC-BY-NC 4.0**。本机个人分析，不赋予商业再利用许可。
- MuQ-MuLan 固定提交 `2e01c796b71dca71b45251384c04cd7b237c9020`，MuQ 骨干固定提交 `0562a57814f6f8bbd9fdea0a25921a2fce1a841a`。原始模型卡保留在对应 models 子目录。
- [FacebookAI/xlm-roberta-base](https://huggingface.co/FacebookAI/xlm-roberta-base) 固定提交 `e73636d4f797dec63c3081bb6ed5c7b0bb3f2089`，保留模型卡和发行包许可。
- 扩展在独立 `.venv-muq` 安装 PyTorch 与 torchaudio；前述“不安装 PyTorch”仅适用于原 `.venv` 的 CLAP 路径。
# HTDemucs 与扩展 DSP（2026-09-13）

- Demucs 4.0.1，Meta 官方项目，MIT；固定源码提交 `ef66d254cd6d558e207eeff2c4b8d053db2e77dd`。上游许可、README、模型索引及模型配置保存于 `models/demucs/`。
- 权重 `955717e8-8726e21a.th`，官方来源 `https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/955717e8-8726e21a.th`，84,141,911 字节。
- 首次以官方 HTTPS、官方文件名 8 字符 SHA-256 前缀核对，完整本地摘要固定为 `8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4`；不是另行声称官方完整签名。
- PyTorch、torchaudio、librosa、NumPy、SciPy、SoundFile、Matplotlib、FFmpeg 及 Demucs 依赖仍保留安装包自身许可。新环境锁文件 `requirements-deep.lock.txt`；项目原创代码的 AGPL-3.0-only 授权见根目录 LICENSE，第三方包保留各自许可。
- DSP 参考：librosa 0.11.0 的 chroma_stft、MFCC、HPSS、pYIN 文档；和声匹配是本地 24 个三和弦模板及 Krumhansl–Kessler 调性轮廓基线，不是下载的和弦分类模型。结构候选为本地色度／音色相似度与局部对比实现，未使用或安装 All-In-One。
- 原音乐及分离／试听衍生文件仅留本机，不随代码或文档公开分发；第三方代码许可不授予原歌曲的传播权。
- 主旋律补充使用已安装的 Essentia.js 0.1.3 官方 WASM（AGPL-3.0，上游许可保存在 `.reference-essentia-js/node_modules/essentia.js/LICENSE`，npm 完整性锁在该目录的 package-lock.json）。MELODIA 与 EqualLoudness 直接调用官方实现，未另行移植算法；参考 https://essentia.upf.edu/tutorial_pitch_melody.html 。
