# OpenWrite

[中文](README.md) · [English](README.en.md)

OpenWrite 是面向 AI Agent 的图文创作工作区，支持微信公众号与小红书。从研究选题、写作、配图到生成可发布产物，再按用户要求上传或发布，资料与成果都保存在项目内。

**在 Agent 中打开本项目即可使用内置 Skill，无需全局安装。** Agent 负责研究、创作和验收，代码检查产物与步骤顺序。

| 平台 | 交付内容 | 发布方式 |
|---|---|---|
| 微信公众号 | Markdown、排版 HTML、独立封面及可选正文配图 | 上传草稿箱，群发在微信后台操作 |
| 小红书 | 笔记文案与 3:4 组图，封面为首图、内容卡片必需 | 发布笔记，默认仅自己可见；公开需明确授权 |

## 快速开始

macOS / Linux 安装 Python 3.9+（建议 3.10+）和 Make 后，在项目根目录运行：

```bash
make setup
make doctor
```

`make setup` 创建或复用 `.venv`、安装依赖，并从 `openwrite.example.yaml` 生成本地 `openwrite.yaml`，不覆盖已有配置。依赖安装需要联网；命令不会填写凭证、生图或发布。

编辑 `openwrite.yaml` 维护平台账号、写作视角及按需使用的服务凭证。配置为嵌套 YAML，每个平台可维护多个账号（凭证、视角、封面样式与排版主题按账号隔离）；模板默认启用微信与自媒体博主，微信还支持技术作者、产品经理、新闻记者与小说家视角（预设在 `writer_roles/`，可增删改），小红书目前支持博主视角。图片来源和发布服务需要各自配置，凭证可等使用前填写。

小红书卡片渲染及发布还需一次性安装浏览器：

```bash
.venv/bin/python -m playwright install chromium
```

手动初始化、Windows PowerShell、看板使用及配置排错见 [环境与运行](docs/setup.md)。`doctor` 只做本地检查，不验证外部服务或凭证。

## 开始创作

将本项目作为工作目录在 Agent 中打开，直接描述需求，例如：

> 帮我写一篇关于 RAG 的公众号文章，面向非技术读者，完成配图和排版。

> 帮我做一篇小红书图文，介绍三个整理读书笔记的方法，完成卡片和文案。

> 继续处理 articles/rag-guide，把开头改得更通俗，再重新排版。

> 把 articles/rag-guide 上传到公众号草稿箱。

正式项目规则统一从 [AGENT_GUIDE.md](AGENT_GUIDE.md) 开始。`AGENTS.md`、`CLAUDE.md`、`GEMINI.md` 仅引导读取该指南；宿主没有自动加载时，先让 Agent 读取 `AGENT_GUIDE.md`。

创作依次经过资料搜索、分析、正文、封面、内容配图、Markdown 和可发布产物七个阶段。默认在写全文前确认标题与大纲；写作和排版不隐含发布授权。实际能力取决于宿主的搜索、文件、命令和图片工具，缺少能力时会保留待办，不声称已经完成。

## 工作区与进度

每个任务保存在独立的 `articles/<名称>/` 中，默认不提交 Git：

```text
articles/<名称>/
├── article.md / article.html / cover.png  # 微信交付件及可选正文图
├── note.md / xhs-*.png                  # 小红书交付件（按平台生成）
├── process/                            # 需求、资料、分析、大纲与草稿
└── workflow/                           # 状态、图片记录与发布清单
```

可通过只读故事板查看任务进度和产物预览。双击 `看板.command` / `看板.sh` / `看板.bat`（macOS / Linux / Windows）启动并打开浏览器，关闭脚本窗口即停止；停止后台实例、端口等见 [看板说明](docs/setup.md#实时故事板)。恢复任务使用：

```bash
.venv/bin/python openwrite.py workflow status articles/rag-guide
```

## 文档导航

| 文档 | 内容 |
|---|---|
| [Agent 指南](AGENT_GUIDE.md) | 正式执行规则、技能路由、确认与交付要求 |
| [环境与运行](docs/setup.md) | 安装、凭证、命令环境、排版选项、故事板与排错 |
| [平台与视角选择](docs/task-selection.md) | 配置优先级、参数与任务快照 |
| [七步工作流](docs/workflow.md) | 阶段产物、JSON 示例、发布检查与返工命令 |
| [配图交接协议](docs/image-contract.md) | 图片需求、结果、来源与验收记录 |
| [微信封面样式](docs/cover-style.md) | 版式、视觉风格、色调与单次覆盖 |
| [平台适配器契约](docs/platforms.md) | 平台规格、代码职责与新增平台接入 |

## 开发验证

```bash
.venv/bin/python -m unittest discover -s tests -v
```

命令入口为 `openwrite.py`；Skill 位于 `skills/`，平台规格位于 `platforms.py`，工作区路径由 `layout.py` 管理。工程开发任务直接修改工程，不进入文章创作流程。

## 许可证

[MIT License](LICENSE)。
