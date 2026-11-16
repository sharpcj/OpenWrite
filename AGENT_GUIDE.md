# OpenWrite Agent 接入指南

OpenWrite 是项目级创作工程，统一入口为 [AGENTS.md](AGENTS.md)。各 Skill 保存在 `skills/` 下，文章保存在 `articles/` 下，无需全局安装。

## 在不同 Agent 中打开

将 OpenWrite 作为项目或工作目录打开。宿主支持自动读取项目说明时，通过对应入口读取 `AGENTS.md`；`CLAUDE.md`、`GEMINI.md` 只转向同一份说明。若宿主没有自动读取机制，直接说：“先阅读项目根目录 AGENTS.md，然后按其中的技能路由执行我的创作需求。”

这是一套项目文件约定，不是通用 Agent SDK，也不要求所有宿主使用相同的 Skill 加载接口。不要为使用 OpenWrite 而把 Skill 复制到全局目录。宿主必须能够读取项目文件，或由用户提供所需文档。

## 平台和视角选择

新任务使用配置中的唯一默认项：运行时只读取本地 `.env`，[.env.example](.env.example) 只是供 `setup` 复制的打样模板，不参与解析。用户提示词明确指定时以其选择优先。Agent 仅把明确选择传为 `--platform` / `--perspective`；配置歧义通过命令返回“需要确认”，必须向用户取得明确选择。详见 [任务选择规则](docs/task-selection.md)。继续任务以已有状态为准，不重选。

## 能力要求

| 工作 | 所需能力 | 缺少能力时 |
|---|---|---|
| 研究与核实 | 搜索、网页读取或用户资料 | 使用已有资料，说明无法核实的信息 |
| 写作 | 文本生成 | 由用户提供正文 |
| 保存产物 | 文件读写 | 提供内容和保存说明，不声称已保存 |
| 本地生图 | 命令执行、Python、可访问的 ComfyUI | 用户选择已配置的宿主生图能力，或保留提示词 |
| 排版 | 命令执行、Python、PyYAML | 提供项目命令供用户执行 |
| 上传草稿 | 命令执行、Python、Requests、网络及公众号凭证 | 交付 HTML、图片和发布命令 |

“搜索”“写文件”“生成图片”描述能力，不是固定 API。工具参数、返回值、凭证及计费由宿主和后端决定。未实际生成的文件或草稿不能作为已完成产物交付。

## 固定写作流程

整体三模块：**下发需求 → 写作 → 发布**。需求与发布需用户确认；写作内部由代码门禁推进，期间仍可按需人工介入。

**搜索资料 → 分析资料 → 写正文 → 生成封面 → 按需生成正文配图 → 生成 Markdown → 排版并保存可发布产物**

三种写作视角共用七步，状态由 `workflow.json` 管理。第三步保存 `draft.md`，前五步产物检查通过后运行 `workflow finalize` 生成 `article.md`（第六步），再运行 `openwrite.py format` 生成 `article.html` 与 `publish-manifest.json` 并自动完成第七步。内容结构图属于按需生成的正文配图，不单独设阶段。工作区初始化或中途暂存不代表可发布产物已交付。

分析完成后、写正文之前有**标题与大纲检查点**：给出三个备选标题（至少一个 `激进悬念`、一个 `客观中性`，第三个默认 `利益实用`）与大纲，用户选定标题并确认大纲后才写全文，可反复讨论修改；记录在 `outline.md` 与 `outline.json`，`draft.md` 的 H1 必须与已确认标题一致。是否启用由 `.env` 的 `OutlineApproval` 控制（默认 `true`），用户明确授权时可用 `new --skip-outline`；选择在创建任务时落盘，之后改配置不影响已有任务。

通过 `workflow status <目录>` 查看进度，通过 `workflow complete <目录> --step <步骤>` 提交前五步；返工使用 `workflow reset <目录> --from <步骤>`。协议与产物示例见 [七步工作流](docs/workflow.md)。每次推进都会检查已完成产物，发现过期时需要退回重做。

## 独立图片能力

只有流程到达 cover/content 时，项目图片入口才允许处理相应图片。按 [配图交接协议](docs/image-contract.md) 提交 `image-requests.json`。项目流程读取 [openwrite-images](skills/openwrite-images/SKILL.md)，执行图片需求后取得图片和 `image-results.json`，再交回写作侧做视觉验收。宿主工具或其他方式取得的图片也按同一需求导入，避免绕开文件与尺寸检查。

```bash
python3 openwrite.py image articles/my-topic --id cover --backend comfyui
python3 openwrite.py image articles/my-topic --id cover --backend file --source /path/to/image.png
```

`--fit exact` 默认拒绝尺寸不符的图片；`contain` 留白适配，`cover` 裁剪适配。后两者必须显式选择，并复查构图和文字。已有图片默认不覆盖。Pillow 负责实际图片解码与尺寸检查，视觉内容仍由写作侧验收。

## 路径与继续创作

- `openwrite.py` 总是相对于自身位置寻找 `skills/` 与 `articles/`，不依赖全局安装目录。
- `new` 总是在项目 `articles/` 下创建文章；`format`、`publish` 的文章目录参数相对于调用时的工作目录，也支持绝对路径。
- 项目创作统一使用根命令，保证阶段检查生效；底层脚本独立使用时不提供相同的流程保证。
- 同一篇文章的工作流状态、需求、资料、分析、`draft.md`、`article.md`、图片及 `article.html` 放在同一目录。更换 Agent 或会话后，先读取该目录需求与产物。
- 正文配图使用同目录相对路径。封面命名为 `cover.png`，不嵌入正文；发布时单独上传。
- 图片能力读取后端输出，校验实际文件后保存到文章目录；如果后端输出在本机不可访问，应报告失败。

## 环境与命令

在项目根目录创建虚拟环境并安装 `requirements.txt`。使用同一 Python 环境调用入口及子脚本。

```bash
python3 openwrite.py doctor
# 需要上传草稿时：生成本地 .env 并填写微信凭证
python3 openwrite.py setup
python3 openwrite.py new my-topic --title "文章标题" --type tech
python3 openwrite.py workflow status articles/my-topic
# 实际完成并按顺序提交前五步后
python3 openwrite.py workflow finalize articles/my-topic
python3 openwrite.py format articles/my-topic --theme default
python3 openwrite.py publish articles/my-topic --title "文章标题"
```

`doctor` 不联网，不确认 ComfyUI 在线或微信凭证有效。`publish` 会实际调用微信 API，只有用户要求上传草稿时才执行。

默认排版器会对全文进行中英文间距和引号预处理，包括代码示例。需要保留原文时用 `format --no-preformat`。项目入口自动执行微信代码块兼容转换。

微信凭证放在项目本地 `.env`：运行 `python3 openwrite.py setup` 从 `.env.example` 复制生成（不覆盖已有文件，权限 600，已被 Git 忽略），再填写 `WeChatAppID`、`WeChatAppSecret`，可选 `WeChatAuthor`。发布器不再读取 `~/.wechat-publisher/config.json`；access_token 缓存仍在 `~/.wechat-publisher/token_cache.json`。图片后端集中配置在 `skills/openwrite-images/`，写作 Skill 只通过 `image-requests.json` 提交设计需求。不要将真实密钥写入 `.env.example` 或加入版本控制，也不代用户填写凭证。

## English

Open the repository in your agent and read [AGENTS.md](AGENTS.md). The skills live in `skills/` and article workspaces in `articles/`; global skill installation is unnecessary. `CLAUDE.md` and `GEMINI.md` redirect to the same project instructions. If the host does not load project instructions automatically, explicitly ask it to read `AGENTS.md`.

Writing skills submit backend-neutral requests to `image-requests.json`. The independent `openwrite-images` capability owns acquisition, backend configuration, decoding, dimension checks, and `image-results.json`. Image readiness still requires visual review.

Map the documented capabilities to the host's actual tools. Report missing capabilities and provide text, prompts, or commands instead of claiming unexecuted work. Continue an article by reading its `brief.md` and existing artifacts.

`openwrite.py` finds its resources relative to the project, independent of the shell working directory. `new` creates a workspace under the project; `format` and `publish` accept a directory relative to the caller or an absolute path. Use one Python environment for the entrypoint and child scripts.

`doctor` performs local checks only. `format` also converts code blocks for WeChat; use `--no-preformat` to preserve original code quotes and spacing. `publish` calls the WeChat API, requires HTML and a cover, and should run when the user requests an upload. Credentials live in the project-local `.env`: run `python3 openwrite.py setup` to copy the tracked `.env.example` template (never overwritten, mode 600, Git-ignored), then fill in `WeChatAppID`, `WeChatAppSecret`, and optionally `WeChatAuthor`. The publisher no longer reads `~/.wechat-publisher/config.json`; the token cache stays at `~/.wechat-publisher/token_cache.json`. Never commit real secrets. Project-local skills still require setup for external services.

Workflow progress is persisted in `workflow.json` across seven stages. Submit the first five with `workflow complete`, inspect with `workflow status`, and redo with `workflow reset --from`. `workflow finalize` generates `article.md` (stage six); `format` produces the publishable artifact and completes stage seven. Between analysis and draft, a title/outline checkpoint requires user approval of three candidate titles and an outline (`outline.md` / `outline.json`), controlled by `OutlineApproval` in `.env` and skippable with `--skip-outline` when authorized. Root image, format and publish commands enforce prerequisite state; `publish` also requires the `publish-manifest.json` fingerprints to match the current artifacts. Low-level scripts remain independent.
