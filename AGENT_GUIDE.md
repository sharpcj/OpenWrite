# OpenWrite Agent 指南

本文件是正式项目规则与技能路由的统一入口。`AGENTS.md`、`CLAUDE.md`、`GEMINI.md` 仅要求先读取本文件；宿主未自动加载时，先让 Agent 读取本文件。具体阶段协议、配置与操作示例按下方链接读取，不预加载整个技能库。

## 先识别任务

OpenWrite 支持微信公众号与小红书图文创作，Skill 位于项目 `skills/`，工作区位于 `articles/`，无需全局安装。

- 工程开发、文档评估或维护：直接处理工程，不启动文章创作流程。
- 新建创作：确定平台、主题、视角、资料、约束与图片来源授权，使用 `openwrite.py new` 落盘。需求已明确的维度沿用用户选择。
- 继续创作或处理指定产物：优先使用用户指定目录，先运行 `workflow status <目录>`，再读 `process/brief.md` 与已有产物。不凭修改时间挑选待发布文章，不覆盖其他任务。
- 用户只要求某个阶段：仅处理已到达的阶段，不能跳过未完成的前置步骤。缺少能力时记录待办，交付实际完成的部分。

## 平台、账号、视角与快照

新任务按 [平台与视角选择](docs/task-selection.md) 解析。平台、账号、视角及流程开关只读取本地 `openwrite.yaml`，`openwrite.example.yaml` 仅供 `setup` 复制，运行时不作回退。配置为嵌套 YAML，按 `defaults → 平台节 → accounts.<账号名> → 任务快照` 合并。

1. 用户明确选择优先，由 Agent 转为 `--platform wechat|rednote`、`--account <账号名>`、`--perspective blogger|tech|product`。未指定的维度不擅自传参；话题词不等于选择意图。
2. 未指定平台时，采用唯一启用项（平台下账号数 ≥ 1 即启用）；零项或多项启用必须向用户确认，不自动选择首项。模板默认启用微信，没有 `openwrite.yaml` 时平台没有默认项。
3. 未指定账号时，平台唯一账号自动选用，多账号用 `default_account`，否则向用户确认。未指定视角时读取 `defaults.writer_role`（微信账号可覆盖），缺省默认自媒体博主，无需确认。微信支持 `blogger` / `tech` / `product` / `news` / `novelist`，小红书仅支持 `blogger`；遇到不支持的组合，说明限制并取得明确选择，不静默切换。
4. 继续任务沿用状态中的平台、账号、视角、流程开关、封面快照、排版主题与角色约束快照，不因 `openwrite.yaml` 后续变化重选；发布按任务账号取凭证。可先用 `preferences` 查看解析结果。

写作视角是数据驱动预设（根目录 `writer_roles/*.yaml`）：每个角色声明显示名与别名、写作约束（软约束，创建任务时写入 brief 的「写作约束（角色预设）」并快照为 `writer_profile`）、结构门禁开关（`gates`）与分平台写作 Skill 路由（`skills`）。增删改 YAML 即增删改可选视角，无需改代码；内容要求由写作 Agent 遵守，门禁由控制器按任务快照执行。

微信封面设计前读取任务样式快照。只把用户明确选择的维度转为 `--cover-layout`、`--cover-visual-style`、`--cover-color-tone`；未确定且有歧义的维度请用户选择。修改当前任务用 `workflow cover-style`，已完成封面须先退回 cover。版式、视觉风格、色调及左文右图验收规则见 [封面样式](docs/cover-style.md)，设计时读取。

微信排版主题按账号 `format_theme` 配置，创建任务时快照；`format` 缺省用快照，`--theme` 显式覆盖并在成功后回写。规则见 [微信排版选项](docs/setup.md#微信排版选项)。

## 按阶段读取 Skill

以任务状态中的平台、视角和当前阶段为准。默认博主视角不因主题涉及技术或产品自动切换；微信长文规则不套用到小红书。

| 任务或阶段 | 项目内 Skill |
|---|---|
| 微信 `blogger` | [wechat-blogger-writer](skills/wechat-blogger-writer/SKILL.md) |
| 微信 `tech` | [wechat-tech-writer](skills/wechat-tech-writer/SKILL.md) |
| 微信 `product` | [wechat-product-manager-writer](skills/wechat-product-manager-writer/SKILL.md) |
| 微信 `news` / `novelist` | [openwrite-generic-writer](skills/openwrite-generic-writer/SKILL.md)（角色约束驱动） |
| 小红书图文 | [rednote-note-writer](skills/rednote-note-writer/SKILL.md) |
| 生成、替换或导入图片，含卡片渲染 | [openwrite-images](skills/openwrite-images/SKILL.md) |
| 微信第四步封面版式与设计预设 | [wechat-cover-designer](skills/wechat-cover-designer/SKILL.md) |
| 微信第七步排版 | [wechat-article-formatter](skills/wechat-article-formatter/SKILL.md) |
| 上传微信草稿 | [wechat-draft-publisher](skills/wechat-draft-publisher/SKILL.md) |
| 发布小红书笔记 | [rednote-publisher](skills/rednote-publisher/SKILL.md) |

小红书第七步由根命令组装与校验已渲染卡片，不调用微信排版 Skill。

## 工作区与状态管理

每篇文章使用独立的 `articles/<名称>/`。根目录放可交付产物，`process/` 放需求、资料与草稿，`workflow/` 放状态、验收与发布记录。完整文件映射由 `layout.py` 管理，见 [工作区目录分层](docs/workflow.md#工作区目录分层)；Skill 中裸文件名按此映射解析，旧平铺目录用 `workflow migrate` 升级。个人文章默认忽略 Git。

所有创作命令通过 `openwrite.py` 执行；不能直接修改 `workflow.json` 或调用底层脚本绕过门禁。同一任务顺序推进，不并发修改状态。`new` 和 `workflow init` 只初始化，不代表正文、图片或可发布产物已完成。

入口与子脚本使用同一 Python 环境。文档中的 `python3` 指已安装依赖的解释器；路径、环境初始化、Windows 限制、凭证与看板操作见 [环境与运行](docs/setup.md)。

## 创作与确认边界

整体为 **下发需求 → 写作 → 发布**。需求与发布须有用户确认；写作内部按代码门禁推进，不因每次执行命令额外询问。

写作共七个阶段：**搜索资料 → 分析资料 → 写正文 → 生成封面 → 生成内容配图 → 生成 Markdown → 生成可发布交付件**。开始推进时读取 [七步工作流](docs/workflow.md)，按当前阶段准备产物、提交并处理检查结果。

- 搜索保存来源及实际提取内容，分析使用 `source:<id>` 关联来源。事实与数据须有依据，不把虚构经历写成作者真实体验。
- 分析后、全文前执行标题与大纲检查点：除非任务已授权跳过，先给出三个候选标题（含 `激进悬念`、`客观中性`，第三个默认 `利益实用`）和大纲，等用户选定标题并确认。每轮更新 `process/outline.md`，确认后写入 `workflow/outline.json`；未确认不写全文，草稿 H1 与确认标题一致。结构化记录及开关规则见 [检查点协议](docs/workflow.md#标题与大纲检查点)。
- 图片阶段只有取得实际图片并完成视觉验收后才提交；不能把需求文件或 `ready` 状态当作验收通过。具体职责见下一节。
- 第六步必须用 `workflow finalize` 整合 Markdown，不能另写最终正文绕过控制器。第七步用 `format` 校验并写入 `workflow/publish-manifest.json`。
- 正文、需求或已完成产物变化后，先 `workflow reset --from <最早受影响步骤>`，再重做下游；文件保留，状态失效。正文变化后复核封面与正文图是否匹配，复用图片也需重新验收。操作见 [返工与恢复](docs/workflow.md#返工与恢复)。

交付形态按平台区分：微信为 `article.md`、`article.html`、独立 `cover.png` 与可选正文图；小红书为 `note.md` 与 `xhs-*.png`，封面是首图，至少一张内容卡片。微信正文配图可为零张，但须明确记录理由；小红书不能选择无需内容卡片。两者均须生成发布清单，只有通过第七步才称为可发布产物。

## 图片职责与验收

写作 Skill 只定义画面内容、尺寸、色调、构图、文字、插入位置或卡片顺序及验收要求，不包含后端、模型或 API 调用。项目流程按 [配图交接协议](docs/image-contract.md) 调度 `openwrite-images`，执行后回交写作侧验收。宿主工具生成或用户提供的图片也通过项目 `image --backend file` 导入。

执行图片需求前读取图片 Skill，核对来源授权、`--fit` 默认行为及覆盖选项；ComfyUI、在线生图、图库、文件和 HTML 卡片后端配置由该 Skill 维护。微信封面不嵌正文；正文图片用同目录相对路径。小红书文案不嵌卡片，组图顺序以发布清单为准。

验收须实际查看图片，核对主题、文字、事实、色调与构图。具备看图能力的 Agent 可自行记录 `--reviewed --note`，无需逐图询问用户；没有看图能力时挂起该步交用户确认，不伪造验收。需求变化后核对需求指纹、实际图片与旧验收，不沿用过期结果。

## 发布与交付

写稿或排版不隐含发布授权。用户明确要求上传草稿或发布笔记后，读取对应发布 Skill，核对当前产物与发布清单指纹一致，再执行根命令 `publish`。确认后产物变化使旧确认失效，须重新完成产物校验并取得发布确认。

微信上传草稿箱，群发由用户在微信后台操作；小红书通过创作服务平台页面发布，默认仅自己可见，公开必须有明确授权并传 `--public`。可先 `--dry-run` 做本地检查。Cookie 失效或执行失败时如实报告，未观察到成功信号不声称已发布。成功记录与检查细节见 [发布协议](docs/workflow.md#发布)。

交付说明已完成阶段、实际产物路径及未完成内容。未生成的图片、文件和草稿不能称为完成；缺少搜索、文件、命令或图片能力时说明缺口，提供已有内容、需求或可继续执行的命令。使用宿主实际工具，不依赖固定 API。凭证只按配置文档存入本地环境，不代填，不写入模板或提交仓库。

## 工程维护与文档分工

| 位置 | 维护内容 |
|---|---|
| `AGENTS.md` / `CLAUDE.md` / `GEMINI.md` | 只引导本指南 |
| `README.md` / `README.en.md` | 项目介绍、快速开始和文档导航，保持中英文对应 |
| 本指南 | Agent 决策规则、技能路由、确认边界与交付要求 |
| `writer_roles/` + `writer_roles.py` | 视角预设（约束、门禁、Skill 路由）与解析器 |
| `docs/setup.md` | 环境、凭证、命令运行、排版选项、看板与排错 |
| 其他 `docs/` | 阶段协议、JSON 示例、选择规则、图片契约与平台接入 |
| `skills/` | 当前阶段的创作方法与底层能力操作 |

新增或改变行为时更新负责该细节的文档，其他位置保留必要概述和链接。平台规格、产物名、尺寸、上限与 Skill 接线以 `platforms.py` 为准；`implemented` 与 `publish_implemented` 分别控制产物及发布支持。接入开发先读 [平台适配器契约](docs/platforms.md)。

优先使用 `--perspective`，`--type` 仅为旧版兼容。按改动范围验证；完整测试命令为 `.venv/bin/python -m unittest discover -s tests -v`。文档改动检查本地链接、锚点、命令与代码是否一致，不为纯文字变更新增实现镜像测试。
