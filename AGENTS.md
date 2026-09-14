# Taste Atlas 开发约定

- 默认中文沟通；先检查实际代码，区分已实现、已验证和计划功能。
- 修改本项目，不同步修改旧工具目录。音频实现同时遵循 audio-analysis/AGENTS.md。
- SOURCE_FILES.json 是源码发布清单；新增源码必须更新清单，并用 tools/source_release.py --write-gitignore 同步规则。
- 不提交模型、环境、音乐、图片、缓存、生成结果、历史验收原件或本机复制清单；不要使用 git add -f 绕过边界。
- 修改发布规则后运行 tools/source_release.py --check 和源码打包检查；.gitignore 不会保护已跟踪文件，正式提交前检查暂存区。
- 仓库为 shuntianyifang/taste-atlas，默认分支 main；推送按任务授权执行。原创代码采用 AGPL-3.0-only，保留第三方署名及独立许可，不擅自改变授权。
- 推理保持本地；不要修改或上传用户素材。模型准确度、相似度和用户偏好不得混淆。
