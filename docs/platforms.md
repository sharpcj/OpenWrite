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

| 平台 | 可选择 | 适配器 | 产物形态 |
|---|---|---|---|
| 微信 `wechat` | ✅ | ✅ 已实现 | 长文：`article.md` → `article.html` + `cover.png`（1024×432，不嵌正文） |
| 小红书 `rednote` | ✅ | ❌ 未实现 | 图文：`note.md` + `cards.md` → 3:4 组图（1080×1440，封面即首图） |

小红书规格已核实并写入注册表，但写作、渲染、发布 Skill 尚未实现，因此 `implemented: false`，`checked()` 等门禁会在任何阶段推进前拒绝，并保留已保存的平台选择。

### 微信（已实现）

- 标题 ≤64 字符 / 192 字节，作者 ≤20 字节，摘要 ≤120 字节，封面 PNG <2MB。
- 正文配图可选，可为零张，但必须在 `content-images.json` 记录决策与理由。
- 代码块必须转换为微信兼容格式（检查 HTML 中不得残留 `<pre`）。
- 发布走官方 API，凭证为 `.env` 的 `WeChatAppID` / `WeChatAppSecret` / `WeChatAuthor`。

### 小红书（规格已定，待实现）

已核实规格：

- 画布 **1080×1440（3:4）**，文字类导出 PNG。
- 安全区：侧边 72–96px、上 72–112px、下 80–120px，文字与关键对象须在安全区内。
- 推荐组图：1 张封面 + 4–8 张内容页，可选总结/清单页。
- 标题 ≤20 字；封面大标题 ≤15 字；内容页标题 12–30 字，配 2–4 条短片段或一段简洁文字。
- 一页一个观点；有截图时减少文字并给足截图面积。
- 发布凭证为创作服务平台 Cookie（`XhsCreatorCookie`），默认「仅自己可见」，公开需显式授权。

**正文长度上限未取得权威来源**，记录在 `unverified: ['desc_chars']`，需实测后再写入 `limits`，不凭印象写死。

与微信的两处语义差异（实现时必须处理）：

1. **封面即组图首图**，不是独立于正文的图；「封面不嵌入正文」规则不适用，且封面与后续卡片须视觉统一。
2. **正文卡片必需**，`needed: false` 分支不允许；长文插入锚点 `placement` 失去意义，改为卡片顺序。

## 适配器职责边界

| 层 | 归属 | 说明 |
|---|---|---|
| 流程与门禁 | `workflow.py` | 平台中立，只查注册表 |
| 命令分派 | `openwrite.py` | `RENDERERS` 按平台注册渲染函数；发布按注册表取 Skill 与入口 |
| 写作表达 | 平台写作 Skill | 方法论与平台表达规格；共享协议链接 `docs/`，不各抄一份 |
| 渲染 | 平台渲染 Skill | 微信 Markdown→HTML；小红书卡片稿→HTML→PNG |
| 发布 | 平台发布 Skill | 各自链路与凭证，互不共用 |
| 图片获取 | `openwrite-images` | 平台中立，尺寸与张数由需求与注册表表达 |

渲染函数签名约定：

```python
def render_<platform>(directory: Path, state: dict, args: argparse.Namespace, staged: Path) -> int
```

在 `staged` 暂存目录产出结果，返回非零表示失败；入口负责可发布性检查、写入正式产物与完成第七步。失败时保留上一次成功的产物。

**已知待扩展点**：`workflow.check_publishable()` 目前假设第七步产出单个渲染文件（微信的 `article.html`）。组图类平台产出多张 PNG，实现 P0 时需把该检查扩展为「逐张校验尺寸/安全区/张数」，而不是复用单文件分支。`rendered_artifact: null` 即用于标识这类平台。

## 新增平台接入清单

1. 在 `platforms.REGISTRY` 增加条目，先置 `implemented: false`，写入已核实规格。
2. 实现写作 Skill（或复用现有视角 Skill + 平台表达规格）。
3. 实现渲染 Skill，并在 `openwrite.RENDERERS` 注册渲染函数。
4. 实现发布 Skill，登记 `publisher` 与 `publisher_entry`。
5. 在 `preferences` 增加平台键与凭证键；`setup` 模板补占位项。
6. 补测试：规格、门禁拒绝、产物指纹、可发布性检查、端到端。
7. 全部通过后将 `implemented` 置为 `true`，并更新 `AGENTS.md`、README 与本文件。

不需要复制 `workflow.py`、图片能力或配图协议。

## 目标目录骨架（小红书）

```text
skills/
├── rednote-note-writer/      # 标题钩子、短正文、话题、卡片分页文案
├── rednote-card-renderer/    # 卡片稿 → HTML → PNG，主题/版式/安全区/校验
└── rednote-publisher/        # Cookie 签名发布，dry-run，默认仅自己可见

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

- **P0｜写作 + 卡片产物（不含自动上传）**：解除门禁 → 写作 Skill → 卡片渲染 → 第七步分派 → 清单。交付即「组图 + 文案」，用户手动发布，零平台风控风险。
- **P1｜发布适配器**：Cookie 配置、`dry-run`、默认仅自己可见、用户授权闸门。
- **P2｜运营增强（可选）**：选题灵感、爆款拆解、知识库沉淀。

## 风险与许可证

- 小红书官方已发布治理 AI 托管运营账号的公告；适配前须让用户知情授权，默认仅自己可见，公开需显式开关。
- 无官方开放 API，Cookie 会过期且有风控；发布失败必须可恢复，不得声称已发布。
- 参考项目许可证：`Auto-Redbook-Skills` 为 MIT（可参考/复用，保留版权声明；其发布实现提取自 `Spider_XHS`，上游许可证需另行核实）；`guizang-social-card-skill` 为 **AGPL-3.0，不得并入本 MIT 项目**，只能借鉴思路独立实现。
- 卡片渲染若采用 HTML + Playwright，将引入 Node.js 与浏览器依赖，需同步扩展 `doctor` 与环境说明。

阶段协议见 [七步工作流](workflow.md)，配图协议见 [配图交接协议](image-contract.md)，平台与视角选择见 [选择规则](task-selection.md)。
