# OpenWrite 项目指南

OpenWrite 是一个微信公众号创作工作区。用户在项目中提出写作、配图、排版或上传草稿需求时，直接使用本项目内的 Skill，无需全局安装。处理工程开发任务时，按用户要求修改工程，不启动文章创作流程。

## 平台与写作视角

新任务先按 [选择规则](docs/task-selection.md) 解析平台与视角。运行时只读取本地 `.env`（由 `setup` 从 `.env.example` 模板复制生成，模板本身不参与解析）；提示词明确指定优先。平台其次采用同组唯一启用项，全部关闭或多项启用且用户未指定时，必须先向用户确认，不自行猜测；写作视角读取单值 `WriterRole`，缺省默认 `SelfMediaBlogger`（自媒体博主），无需确认。

用户提示词中的明确选择由 Agent 转为 `new` / `workflow init` 的 `--platform wechat|rednote` 和 `--perspective blogger|tech|product`；未指定的维度不要擅自传参，以免覆盖默认配置。话题词不等于选择意图，例如分析某平台不等于发布到该平台。

默认配置是微信与自媒体博主。确定后由代码写入任务状态，继续任务时沿用，不因默认文件变化而更改。运行 `preferences` 可先查看解析结果；命令提示需要确认时，向用户取得明确选择再继续，不自动选择列表第一项。

微信已完整接入（写作→排版→上传草稿）。小红书已完整接入（写作→卡片产物→发布），交付「3:4 组图 + 笔记文案」；发布通过创作服务平台页面自动化完成，**默认仅自己可见，公开需用户显式授权（`--public`）**，未实际观察到成功信号不得声称已发布。不能代替用户切换平台，也不能把微信长文规则套用到小红书图文。

平台差异由根目录 `platforms.py` 的注册表表达（产物形态、尺寸、张数、上限、渲染与发布 Skill），控制器与命令入口只查表，不散落平台判断。`implemented` 管写作到可发布产物，`publish_implemented` 管上传，两者独立。接入方式与路线见 [平台适配器契约](docs/platforms.md)。

## 技能路由

优先读取任务状态中的平台与视角，再按当前阶段读取 Skill，不预先加载整个技能库。

| 微信任务的视角或阶段 | 项目内 Skill |
|---|---|
| 自媒体博主 `blogger`（默认；包括其技术或产品话题） | [wechat-blogger-writer](skills/wechat-blogger-writer/SKILL.md) |
| 技术作者 `tech` | [wechat-tech-writer](skills/wechat-tech-writer/SKILL.md) |
| 产品经理 `product` | [wechat-product-manager-writer](skills/wechat-product-manager-writer/SKILL.md) |
| 小红书图文（`rednote` 平台） | [rednote-note-writer](skills/rednote-note-writer/SKILL.md) |
| 第七步排版、生成公众号 HTML 与可发布产物 | [wechat-article-formatter](skills/wechat-article-formatter/SKILL.md) |
| 生成、替换或导入图片，执行配图需求 | [openwrite-images](skills/openwrite-images/SKILL.md) |
| 上传微信公众号草稿箱 | [wechat-draft-publisher](skills/wechat-draft-publisher/SKILL.md) |
| 发布小红书笔记（默认仅自己可见） | [rednote-publisher](skills/rednote-publisher/SKILL.md) |

## 文章工作区

- 每篇文章使用独立的 `articles/<名称>/` 目录。优先使用用户指定的已有文章；新建文章可运行 `python3 openwrite.py new <名称> --title "标题"`，仅在用户明确指定时传入 `--platform` 或 `--perspective`。
- `brief.md` 保存主题、受众、视角、资料和用户约束；`outline.md` / `outline.json` 保存标题候选、大纲与用户确认；`draft.md` 保存正文草稿，`article.md` 为最终整合结果；`image-requests.json` 保存设计需求，`image-results.json` 保存图片执行结果；封面为 `cover.png`；可选内容结构图为 `structure.png`；其他配图用有含义的文件名；排版输出为 `article.html`，发布清单为 `publish-manifest.json`。
- 新建命令只创建工作区和初始文件，不代表正文或图片已完成。不要覆盖另一篇文章的成果，也不要凭文件修改时间选择待发布文章。
- Markdown 中正文配图使用同目录的相对路径；封面不嵌入正文，发布时单独上传。
- 文章目录默认不进入 Git，技能代码与个人创作产物分开存放。跨会话或跨 Agent 继续任务时，先运行 `workflow status <文章目录>`，再阅读 `brief.md` 和已有产物。

## 创作流程

整体分三个模块：**下发需求 → 写作 → 发布**。需求与发布需要用户确认，写作内部由代码门禁推进，期间仍可按需人工介入。

- **下发需求**：确定平台、主题、写作视角，以及资料、约束和图片来源授权；由 `new` / `workflow init` 落盘。
- **写作**：七步工作流，最终交付**可发布产物**（`article.html` + `cover.png` + `publish-manifest.json`）。
- **发布**：用户明确确认后运行 `publish`；微信上传草稿箱（群发仍在微信后台操作），小红书发布笔记（默认仅自己可见，公开需显式 `--public`，可先 `--dry-run` 预演）。

三种微信写作视角统一固定为：

**搜索资料 → 分析资料 → 写正文 → 生成封面 → 按需生成正文配图 → 生成 Markdown → 排版并保存可发布产物**

1. **搜索资料**：将来源及实际提取内容保存为 `sources.json`，完成后运行 `workflow complete <目录> --step search`。
2. **分析资料**：保存 `analysis.md`，用 `source:<id>` 关联已有来源；提交 `--step analysis`。
3. **写正文**：先经过**标题与大纲检查点**（见下），取得用户确认后按写作 Skill 完成 `draft.md`，不嵌入图片；提交 `--step draft`。不把虚构经历写成作者的真实体验。
4. **生成封面**：写作 Skill 根据正文定义封面需求，写入 `image-requests.json`。项目流程读取 `openwrite-images` 并取得 `cover.png`，再按写作规则进行视觉验收；提交 `--step cover --reviewed --note "验收说明"`。封面不嵌入正文。
5. **按需生成正文配图**：写作 Skill 判断需要哪些图并定义设计要求，可以为零张。项目流程逐项调用 `openwrite-images`，取得图片后回交写作侧验收。结构图属于可选正文配图。保存 `content-images.json` 明确是否需要及理由；需要图片时取得并验收后提交 `--step content --reviewed --note "验收说明"`，无需图片时提交 `--step content`。
6. **生成 Markdown**：运行 `workflow finalize <目录>`，由程序整合 `draft.md` 和已验收正文配图，生成 `article.md` 并完成第六步。不要自行另写最终正文以绕过控制器。
7. **排版并保存可发布产物**：运行 `python3 openwrite.py format <目录> --theme default`，调用排版 Skill 生成 `article.html`，执行可发布性检查，写入 `publish-manifest.json` 并自动完成第七步。检查不通过时保留上一次成功的 HTML，不推进状态。

### 标题与大纲检查点（分析之后、写正文之前）

除非用户已授权跳过，必须先取得用户对标题和大纲的确认，再生成正文全文：

- 给出**三个备选标题**：至少一个激进、有悬念、吸引点击的（风格标注 `激进悬念`），一个相对客观中性的（`客观中性`），第三个默认利益实用型（`利益实用`）。
- 同时列出大纲，交用户选择标题（也可自定义）并确认大纲；用户可反复提修改意见，每轮更新 `outline.md`，直到确认。未确认前不生成全文。
- `outline.md` 保存候选标题、大纲、讨论与修改记录、最终确认内容；`outline.json` 保存结构化确认（候选与风格、`chosen_title`、`title_source`、`approved`、`outline.md` 指纹）。
- 代码在提交 `draft` 时校验确认记录，并要求 `draft.md` 的 H1 与已确认标题一致；选定标题同步到任务状态，供排版与发布使用。确认后修改大纲会使正文及下游失效。
- 是否启用由 `.env` 的 `OutlineApproval` 控制（默认 `true`）；用户明确授权跳过时可用 `new --skip-outline`。该选择在创建任务时写入状态，之后改配置不影响已有任务。

所有上述命令以 `python3 openwrite.py` 开头。阶段协议、文件示例与返工方法见 [七步工作流](docs/workflow.md)。状态由代码检查并推进，不直接修改 `workflow.json`；图片、排版和上传统一使用项目入口，避免绕过状态检查。图片验收可由具备看图能力的 Agent 完成并记录，不需要每一步都询问用户；无看图能力时不得伪造验收，应挂起该步交用户确认。

选题理解属于搜索前的准备，不另增流程步骤。新建命令生成的标题占位文件不视为最终 Markdown。用户只要求某个阶段时，处理已到达的阶段并暂停；不能跳过未完成的前置步骤。修改已完成产物后，使用 `workflow reset <目录> --from <步骤>` 退回重做；文件保留，下游状态失效。

七步完成后产物即为可发布状态。用户要求上传草稿或发布笔记时，再读取对应发布 Skill，核对 `publish-manifest.json` 与当前产物一致后执行；写稿或排版不隐含上传。产物在确认后被修改时，旧确认失效，需重新排版并重新取得用户确认。小红书发布还需 `.env` 中的 `XhsCreatorCookie`；Cookie 失效或发布失败时如实报告，不声称已发布。

交付时说明完成阶段、产物路径和未完成内容。图片或草稿未实际生成时，不声称已完成；正文变更后检查封面及正文配图是否仍匹配。

## 配图职责与交接

写作 Skill 只维护画面内容、尺寸、色调、构图、文字、插入位置及验收规则，不包含图片后端或工具调用。项目流程负责调度独立图片能力，按 [配图交接协议](docs/image-contract.md) 传递需求与结果。ComfyUI、宿主工具、已有图片及备用 API 的接入仅由 `openwrite-images` 管理。

图片结果的 `ready` 只表示文件和尺寸校验通过，不能替代视觉验收。需求变更后应核对需求指纹、实际图片及原验收结果，避免沿用过期配图。

## 工具与运行

- 使用当前 Agent 实际提供的搜索、网页读取、文件读写、命令执行和生图能力，不依赖固定工具 API。
- 项目命令入口为 `openwrite.py`。运行 `python3 openwrite.py doctor` 可检查本地依赖、技能入口与模板；该检查不联网、不验证公众号凭证或 ComfyUI 在线状态。
- 首次使用可在根目录创建虚拟环境并安装 `requirements.txt`，之后使用该环境的 Python。命令入口与 Skill 子脚本应使用同一 Python 环境。
- `skills/<技能名>/scripts/` 路径以对应技能目录为基准；`openwrite.py` 的路径参数相对于当前工作目录。不要依赖全局 Skill 目录。
- 若没有命令执行能力，提供命令和产物内容供用户继续；若缺少搜索或生图能力，说明缺口并保留资料需求或提示词，不伪造执行结果。
- 微信凭证与平台、视角共用项目配置：`python3 openwrite.py setup` 把 `.env.example` 复制为本地 `.env`（不覆盖、权限 600、Git 忽略），真实 `WeChatAppID`、`WeChatAppSecret`、`WeChatAuthor` 只写在 `.env`。不要把密钥写入模板或提交到仓库，也不代用户填写凭证。无需全局安装 Skill，也不表示无需配置外部服务。

详细环境、命令和能力说明见 [AGENT_GUIDE.md](AGENT_GUIDE.md)。
