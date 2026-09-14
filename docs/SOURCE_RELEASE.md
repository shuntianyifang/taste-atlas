# 源码发布边界

根目录是项目边界。保留现有 audio-analysis 目录以维持相对模型路径与入口，不为展示结构而搬动运行数据。

采用逐文件允许清单，未列入 SOURCE_FILES.json 的文件默认忽略。允许的是原创源码、测试程序、锁文件、标签词表、模型下载脚本、公开文档和 Essentia.js 的 package.json/package-lock.json。node_modules 和第三方下载内容不打包。

本机 tmp/、模型、环境、缓存、selftest/ 生成数据、results/、COPY_MANIFEST.json、LOCAL_README.md 和历史验收记录全部排除。根 STATUS.md 提供不含绝对本机路径的状态摘要。

## 操作

1. `python tools/source_release.py --check` 检查发布清单、文件类型、大小、常见凭据与本机旧路径，以及 Git 规则是否同步。
2. `python tools/source_release.py --output dist/taste-atlas-source.zip` 生成只包含清单文件的 ZIP，逐项核对归档名称和内容。
3. 后续明确建立仓库后，提交前检查 `git status --short` 和 `git diff --cached --name-only`。不要强制添加被忽略文件。此工具在已有仓库内会拒绝已跟踪或暂存但不在清单中的文件。

新的文件默认不会发布。确需纳入时手动编辑清单，再运行 `--write-gitignore`。不要把素材或凭据加入清单。规则和扫描只是防误操作措施，不能替代提交内容审阅；Git 忽略规则不影响早已进入历史的文件。

源码仓库为 https://github.com/shuntianyifang/taste-atlas，默认分支 main；只发布源码，不创建模型或音乐发行附件。原创代码采用 AGPL-3.0-only，第三方许可和模型使用限制见 audio-analysis/THIRD_PARTY.md。尚未完成干净机器运行验收。

自动验收：`python tools/test_source_release.py`。该脚本仅在系统临时目录创建测试仓库元数据，不在项目内初始化 Git，也不访问远端。
