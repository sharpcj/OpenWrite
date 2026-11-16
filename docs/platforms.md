# 平台适配器契约

OpenWrite 的流程秩序是平台中立的，产物形态按平台分派。本文件定义注册表、适配器职责与新增平台的接入方式。

**原则：秩序共享、产物分平台、差异用数据表达。**

- 共享：七步顺序、状态与指纹、返工规则、标题与大纲检查点、配图交接协议、图片获取与校验。
- 分平台：写作表达规格、渲染/排版实现、发布链路、产物集合与可发布性限制。
- 数据化：尺寸、张数、标题上限、产物文件名等差异写在 `platforms.REGISTRY`，不写成散落的 `if platform == ...`。

## 注册表

唯一位置为根目录 `platforms.py` 的 `REGISTRY`。控制器（`workflow.py`）与命令入口（`openwrite.py`）只读这张表。

| 字段 | 含义 |
|---|---|
| `label` | 平台中文名，与 `preferences.PLATFORM_LABELS` 一致 |
| `implemented` | 写作→可发布产物的适配器是否已实现；`false` 时可选择并记录，但所有门禁拒绝推进 |
| `publish_implemented` | 上传适配器是否已实现；与 `implemented` 独立，可发布产物就绪不等于存在上传路径 |
| `format_label` | 第七步的平台化名称（微信「排版…」，小红书「组装…」） |
| `writers` | 视角 → 写作 Skill 名 |
| `renderer` / `publisher` / `publisher_entry` | 渲染与发布 Skill 及入口脚本 |
| `markdown_artifact` | 第六步整合产物名 |
| `rendered_artifact` | 第七步渲染产物名；组图类平台为 `null` |
| `artifacts` / `optional_artifacts` | 参与发布指纹校验的产物集合 |
| `cover` / `content_size` | 封面约定（id、文件名、尺寸）与正文图默认尺寸 |
| `content_images` | 正文图是否必需、最少/最多张数 |
| `limits` | 标题字符/字节、作者字节、摘要字节、封面字节上限；`null` 表示不校验 |
| `checks` | 平台专属检查开关（如代码块是否必须转换） |
| `author_key` / `credential_keys` | 作者名对应的凭证键（无作者概念时为 `null`）与所需凭证键 |
| `unverified` | 尚未取得权威来源、暂不写入 `limits` 的项 |

辅助函数：`spec(platform)`、`for_state(state)`、`require_pipeline(state)`、`writer_skill(state)`、`limits(state)`。

## 当前平台状态

| 平台 | 可选择 | 写作→可发布产物 | 上传 | 产物形态 |
|---|---|---|---|---|
| 微信 `wechat` | ✅ | ✅ | ✅ | 长文：`article.md` → `article.html` + `cover.png`（1024×432，不嵌正文） |
| 小红书 `rednote` | ✅ | ✅ | ✅ | 图文：`note.md` + `cards.md` → 3:4 组图（1080×1440，封面即首图） |

小红书写作、卡片产物与发布适配器均已实现：卡片由 `openwrite-images` 的 `html` 后端渲染，第七步只组装与校验；发布由 `rednote-publisher` 通过创作服务平台发布页自动化完成（Playwright，站点自身签名），**默认仅自己可见，公开需显式 `--public` 授权**，支持 `--dry-run` 预演。

`implemented` 与 `publish_implemented` 是两个独立开关：前者管写作到可发布产物，后者管上传。可发布产物就绪不等于存在上传路径。

### 微信（已实现）

- 标题 ≤64 字符 / 192 字节，作者 ≤20 字节，摘要 ≤120 字节，封面 PNG <2MB。
- 正文配图可选，可为零张，但必须在 `content-images.json` 记录决策与理由。
- 代码块必须转换为微信兼容格式（检查 HTML 中不得残留 `<pre`）。
- 发布走官方 API，凭证为 `.env` 的 `WeChatAppID` / `WeChatAppSecret` / `WeChatAuthor`。

### 小红书（写作、卡片产物与发布均已实现）

已核实规格：

- 画布 **1080×1440（3:4）**，文字类导出 PNG。
- 安全区：侧边 72–96px、上 72–112px、下 80–120px，文字与关键对象须在安全区内。
- 标题 ≤20 字；封面大标题 ≤15 字；内容页标题 12–30 字，配 2–4 条短片段或一段简洁文字。
- 常规图文笔记正文 ≤1000 字（话题以 `#名称[话题]#` 计入）、单篇图片 ≤18 张（封面 + 内容，注册表 `content_images.max: 17`）。多个公开来源一致；「长文笔记」6000 字为另一内测功能，不适用本组图形态。
- 一页一个观点；有截图时减少文字并给足截图面积。
- **张数由内容动态决定**（注册表 `min: 1`、`max: 17`），不固定 4~8 张。
- 发布凭证为创作服务平台 Cookie（`XhsCreatorCookie`，需含 `a1` 与登录凭证），默认「仅自己可见」，公开需显式授权。

与微信的两处语义差异（已实现）：

1. **封面即组图首图**（`xhs-01-cover.png`），不是独立于正文的图；「封面不嵌入正文」规则不适用，封面与后续卡片须视觉统一。
2. **正文卡片必需**，`needed: false` 分支不允许；长文插入锚点 `placement` 不适用，改为 **`order`**（封面第 1，内容卡片从 2 开始且不可重复）。

第七步对小红书是**组装**而非渲染：卡片已在第 4/5 步由 `html` 后端产出，第七步只确定顺序、校验可发布性并写清单。步骤标签由注册表 `format_label` 提供（微信「排版并保存可发布产物」，小红书「组装并保存可发布产物」）。

## 适配器职责边界

| 层 | 归属 | 说明 |
|---|---|---|
| 流程与门禁 | `workflow.py` | 平台中立，只查注册表 |
| 命令分派 | `openwrite.py` | `RENDERERS` 按平台注册渲染函数；发布按注册表取 Skill 与入口 |
| 写作表达 | 平台写作 Skill | 方法论与平台表达规格；共享协议链接 `docs/`，不各抄一份 |
| 渲染 | 微信：排版 Skill；小红书：`openwrite-images` 的 `html` 后端 | 微信 Markdown→HTML 在第七步；小红书卡片 HTML→PNG 在第 4/5 步 |
| 发布 | 平台发布 Skill | 各自链路与凭证，互不共用 |
| 图片获取与卡片渲染 | `openwrite-images` | 平台中立，尺寸、张数、顺序由需求与注册表表达 |

单文件渲染平台的函数签名约定：

```python
def render_<platform>(directory: Path, state: dict, args: argparse.Namespace, staged: Path) -> int
```

在 `staged` 暂存目录产出结果，返回非零表示失败；入口负责可发布性检查、写入正式产物与完成第七步。失败时保留上一次成功的产物。

**组图平台不走这条路径**：`rendered_artifact: null` 时，第七步调用 `assemble_card_set()`，只做组装与校验；`check_publishable()` 分派到 `check_card_set()`，逐张校验尺寸/格式/顺序并核对笔记文案。卡片渲染发生在第 4/5 步，由 `html` 后端完成，并在渲染期做真实 DOM 版式校验（溢出、字号下限、安全区）。

## 新增平台接入清单

1. 在 `platforms.REGISTRY` 增加条目，先置 `implemented: false`，写入已核实规格。
2. 实现写作 Skill（或复用现有视角 Skill + 平台表达规格）。
3. 渲染二选一：单文件产物 → 实现渲染函数并注册到 `openwrite.RENDERERS`；组图产物 → 复用 `openwrite-images` 的 `html` 后端，置 `rendered_artifact: null`。
4. 实现发布 Skill，登记 `publisher` 与 `publisher_entry`，并置 `publish_implemented: true`。
5. 在 `preferences` 增加平台键与凭证键；`setup` 模板补占位项。
6. 补测试：规格、门禁拒绝、产物指纹、可发布性检查、端到端。
7. 写作链路通过后置 `implemented: true`；上传链路通过后再置 `publish_implemented: true`，并更新 `AGENTS.md`、README 与本文件。

不需要复制 `workflow.py`、图片能力或配图协议。

## 目录骨架（小红书）

```text
skills/
├── rednote-note-writer/          # 已实现：标题钩子、短文案、话题、卡片分页稿
├── openwrite-images/             # 已实现：html 后端 + render_card.py + 卡片模板
│   └── references/card-rendering.md
└── rednote-publisher/            # 已实现（P1）：发布页自动化，dry-run，默认仅自己可见

articles/<名称>/
├── note.md                   # 笔记文案：标题 + 正文 + 话题
├── cards.md                  # 分页卡片稿
├── xhs-01-cover.png          # 封面即首图
├── xhs-02-<topic>.png        # 内容页
├── image-requests.json       # 复用现有协议，尺寸 1080×1440
└── publish-manifest.json     # 元数据（title/desc/topics/images）+ 指纹
```

图片输出仍须是文章同目录下的扁平 PNG 文件名（现有配图协议约束），不使用子目录。

## 分阶段路线

- **P0｜写作 + 卡片产物（不含自动上传）**：✅ 已完成。注册表分派 → `rednote-note-writer` → `html` 后端渲染卡片 → 第七步组装与校验 → `publish-manifest.json`。
- **P1｜发布适配器**：✅ 已完成。`XhsCreatorCookie` 配置、`--dry-run` 预演、默认仅自己可见（失败即中止）、`--public` 显式授权、失败截图与可恢复重试；`publish_implemented: true`。实现为独立编写的 Playwright 发布页自动化（站点自身签名，不引入 Node.js）；UI 流程用本地模拟页做端到端测试，真实账号首次使用建议先私密实测。
- **P2｜运营增强（可选）**：选题灵感、爆款拆解、知识库沉淀。

## 风险与许可证

- 小红书官方已发布治理 AI 托管运营账号的公告；发布前须让用户知情授权，默认仅自己可见，公开需显式开关。
- 无官方开放 API，Cookie 会过期且有风控；发布失败必须可恢复，不得声称已发布。适配器以站点成功信号为准报告结果，失败保留截图。
- 参考项目许可证（已核实）：`Auto-Redbook-Skills` 为 MIT，仅借鉴其默认私密 + 显式公开的产品设计与 Cookie 字段要求；其 vendored 发布运行时提取自 `Spider_XHS`，而 **`Spider_XHS` 无许可证（license: null，保留所有权利）**，不得复制其代码、JS 或指纹材料。`guizang-social-card-skill` 为 **AGPL-3.0，不得并入本 MIT 项目**。本项目发布器与卡片模板均为独立编写，仅参考公开的协议事实（页面地址、可见性语义）。
- 发布与卡片渲染均使用 **Python 版 Playwright + Chromium**，不引入 Node.js。依赖已写入 `requirements.txt`，浏览器需一次性 `python -m playwright install chromium`；`doctor` 会报告就绪状态，缺依赖时只提示不自动下载。

阶段协议见 [七步工作流](workflow.md)，配图协议见 [配图交接协议](image-contract.md)，平台与视角选择见 [选择规则](task-selection.md)。
