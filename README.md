# OpenWrite

[中文](README.md) · [English](README.en.md)

OpenWrite 是一个面向 AI Agent 的微信公众号创作工程。**在 Agent 中打开这个项目，即可按项目内的技能开展文章创作，无需安装全局 Skill。**

从研究选题、写正文、生成配图，到排版和上传微信草稿，文章及其配图都保存在项目自己的工作区中。

## 开始创作

1. 将本项目作为工作目录在 Agent 中打开。
2. 让 Agent 读取根目录的 [AGENTS.md](AGENTS.md)，然后直接描述创作需求。能够自动加载项目说明的宿主会使用相应入口；若未自动读取，明确说“先读取 AGENTS.md”。
3. Agent 按需求读取 `skills/` 下的技能，在 `articles/` 下创建文章目录并开始工作。

例如：

> 帮我写一篇关于 RAG 的公众号技术文章，面向非技术读者，保存到 articles/rag-guide，完成配图和排版。

> 从产品经理视角拆解一个 AI 搜索产品，先写正文。

> 继续处理 articles/rag-guide，把正文改得更通俗，再重新排版。

> 把 articles/rag-guide 上传到公众号草稿箱，标题是“知识库怎么让 AI 回答得更准”。

`AGENTS.md` 维护统一工作约定；`CLAUDE.md` 和 `GEMINI.md` 仅引导读取同一入口。不同宿主加载项目说明的机制不同；不自动加载时，手动要求读取入口即可。完整能力取决于 Agent 的文件、命令、搜索和生图工具，详见 [Agent 接入指南](AGENT_GUIDE.md)。

## 项目结构

```text
OpenWrite/
├── AGENTS.md                       # 统一创作流程与技能路由
├── CLAUDE.md                       # 指向统一入口
├── GEMINI.md                       # 指向统一入口
├── AGENT_GUIDE.md                  # 运行与接入说明
├── openwrite.py                    # 项目命令入口
├── workflow.py                     # 七步状态与产物检查
├── preferences.py                  # 平台与视角默认值解析
├── .env.example                    # 配置占位模板：平台、视角、微信凭证
├── .env                            # 本地真实配置，由 setup 生成，Git 忽略
├── requirements.txt
├── skills/
│   ├── wechat-blogger-writer/
│   ├── wechat-tech-writer/
│   ├── wechat-product-manager-writer/
│   ├── wechat-article-formatter/
│   ├── wechat-draft-publisher/
│   └── openwrite-images/
├── articles/                       # 每篇文章独立目录，默认不提交 Git
└── tests/                          # 工作区命令验证
```

原有四个 Skill 的名称和自身目录名保持不变，新增独立的 `openwrite-images` 图片能力，作为工程内部能力按需读取，无需复制到用户级技能目录。

| Skill | 职责 |
|---|---|
| [wechat-blogger-writer](skills/wechat-blogger-writer/SKILL.md) | 默认自媒体博主视角，注重易读性、观点与实际价值 |
| [wechat-tech-writer](skills/wechat-tech-writer/SKILL.md) | 技术科普、工具介绍；封面必需，正文配图按需 |
| [wechat-product-manager-writer](skills/wechat-product-manager-writer/SKILL.md) | 产品视角、真实场景；封面必需，正文配图按需 |
| [wechat-article-formatter](skills/wechat-article-formatter/SKILL.md) | Markdown 转公众号 HTML，四套 YAML 主题 |
| [openwrite-images](skills/openwrite-images/SKILL.md) | 接收配图需求，获取、校验并保存图片；集中管理后端 |
| [wechat-draft-publisher](skills/wechat-draft-publisher/SKILL.md) | 上传封面、正文图片和微信草稿 |

## 默认平台与写作视角

运行时**只读取本地 `.env`**；[.env.example](.env.example) 只是打样模板，不参与解析。运行 `python3 openwrite.py setup` 会把模板复制为 `.env`（不覆盖已有文件，权限 600，已被 Git 忽略），随后所有平台、视角与凭证的修改都在 `.env` 中进行。模板给出的样例是 `WeChat=true`、`SelfMediaBlogger=true`，其他项关闭。没有 `.env` 时没有默认项，命令会要求用户明确选择。

**本次提示词明确指定 > 配置中唯一启用项 > 用户明确确认**。平台与视角分别判断；同组全部关闭或同时启用多个时，未指定的维度需要确认。

```bash
python3 openwrite.py preferences
python3 openwrite.py new my-topic --title "文章主题"
# 用户明确指定产品经理视角时，覆盖本次任务视角，不改长期配置
python3 openwrite.py new product-topic --title "产品主题" --perspective product
```

选择写入任务状态，继续任务不受后来默认配置修改影响。小红书可选择并记录，但对应创作和发布适配尚未实现，不能调用微信流程继续。详见 [平台与视角选择](docs/task-selection.md)。

## 环境准备

文本写作可以先开始；执行生图、排版和发布脚本时需要相应运行环境。

```bash
python3 -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell 使用 .venv\Scripts\Activate.ps1
python3 -m pip install -r requirements.txt
python3 openwrite.py doctor
# 需要上传草稿时，生成本地配置并填写微信凭证
python3 openwrite.py setup
```

需要 Python 3.8+。核心依赖为 PyYAML、Requests 和 Pillow。`doctor` 只检查本地依赖、技能入口和模板，不调用 ComfyUI 或微信 API。`setup` 只复制配置模板，不联网、不写入任何密钥。

## 文章工作区

每篇文章的资料、正文与图片保存在一起，便于更换 Agent 后继续处理：

```text
articles/rag-guide/
├── brief.md             # 需求、资料、约束、进展与待办
├── workflow.json        # 代码管理的七步状态
├── outline.md           # 备选标题、大纲与讨论记录
├── outline.json         # 用户对标题与大纲的确认记录
├── sources.json         # 来源及实际提取内容
├── analysis.md          # 资料分析与来源关联
├── draft.md             # 第三步正文草稿（不嵌图）
├── article.md           # 第六步由程序整合生成
├── publish-manifest.json # 第七步：可发布产物的元数据与指纹
├── image-requests.json  # 写作侧定义的配图需求
├── image-results.json   # 图片能力返回的实际结果
├── cover.png            # 单独上传，不嵌入正文
├── structure.png        # 按需生成的正文结构图
├── architecture.png     # 按需生成的正文配图
├── content-images.json  # 是否需要正文配图及理由
└── article.html         # 最终排版结果
```

整体分三个模块：**下发需求 → 写作 → 发布**。需求与发布需要用户确认；写作是七步工作流，最终交付可发布产物。

三种写作视角统一固定为：

**搜索资料 → 分析资料 → 写正文 → 生成封面 → 按需生成正文配图 → 生成 Markdown → 排版并保存可发布产物**

分析完成后、写正文之前有一个**标题与大纲检查点**：给出三个备选标题（至少一个激进悬念、一个客观中性，第三个默认利益实用）与大纲，由用户选定标题并确认大纲后才生成全文，可反复讨论修改。是否启用由 `.env` 的 `OutlineApproval` 控制（默认开启），用户明确授权时可用 `new --skip-outline` 跳过。

结构图属于可选正文配图，不再强制生成。第七步完成即代表产物可发布；上传仍需用户明确确认。用户可以只要求其中一个阶段，或继续未完成阶段；没有实际生成的图片不能当作已交付产物。

文章目录默认忽略 Git，避免将个人稿件混入工程源码。需要共享稿件时，可以单独管理或明确加入版本控制。

## 按步骤推进

Agent 仍负责研究、分析、写作和验收，代码负责检查产物与顺序。每篇文章通过 `workflow.json` 持久化进度，不需要数据库。

```bash
python3 openwrite.py new rag-guide --title "知识库怎么让 AI 回答得更准" --type tech
python3 openwrite.py workflow status articles/rag-guide

# 实际搜索并写入 sources.json 后，提交第一步
python3 openwrite.py workflow complete articles/rag-guide --step search
# 完成 analysis.md 后提交第二步
python3 openwrite.py workflow complete articles/rag-guide --step analysis
# 给出三个备选标题与大纲（outline.md / outline.json），用户确认后再写 draft.md
python3 openwrite.py workflow complete articles/rag-guide --step draft

# 取得封面并实际检查画面后提交
python3 openwrite.py workflow complete articles/rag-guide --step cover --reviewed --note "标题、色调和构图符合要求"
# 明确无需正文配图时，先保存 content-images.json 的决策和理由
python3 openwrite.py workflow complete articles/rag-guide --step content
# 需要配图时应先取得并验收，提交时加 --reviewed --note

# 第六步：整合生成 article.md
python3 openwrite.py workflow finalize articles/rag-guide
# 第七步：排版、可发布性检查、写入 publish-manifest.json 并自动完成
python3 openwrite.py format articles/rag-guide --theme default
# 保留正文和代码的原始引号、间距可加 --no-preformat
# 只有用户明确确认发布时执行；标题默认取自已确认的发布清单
python3 openwrite.py publish articles/rag-guide
```

不能跳步；产物不完整不会推进。正文配图可以没有，但必须明确记录理由。图片是否符合主题、文字和构图由执行者实际检查，代码记录其验收确认，不自动判断内容质量。第七步还会检查标题/作者/摘要长度、封面大小与格式、代码块转换和本地图片是否存在，不通过则保留上一次成功的 HTML。

需要修改正文时：

```bash
python3 openwrite.py workflow reset articles/rag-guide --from draft
```

退回保留文件，清除该阶段及下游状态。内容指纹会检测已完成产物是否变化，防止沿用过期配图或排版；更换 Agent 后通过 `status` 继续。现有文章可用 `workflow init <目录>` 初始化，再按步骤提交已有产物。只换主题重排版时 `reset --from format` 即可；产物在用户确认后被修改，需重新排版并重新确认发布。

完整文件协议与示例见 [七步工作流](docs/workflow.md)。主题支持 `default`、`grace`、`modern`、`simple`。可用 `python3 openwrite.py --help` 查看命令。

## 配图与发布配置

写作 Skill 定义“配什么图”，独立的 [openwrite-images](skills/openwrite-images/SKILL.md) 负责“图片怎么来”。两者通过 [配图交接协议](docs/image-contract.md) 协作，写作 Skill 不感知后端配置、模型与 API 参数。

```bash
# 按当前文章的 image-requests.json 执行一项图片需求
python3 openwrite.py image articles/rag-guide --id cover --backend comfyui
# 宿主工具、绘图软件或用户提供图片后，按同一需求导入并校验
python3 openwrite.py image articles/rag-guide --id cover --backend file --source /path/to/cover.png
```

图片能力集中保留 ComfyUI 和 Gemini / DALL-E 备用实现，配置唯一位置为 `skills/openwrite-images/config.json`。宿主工具通过其实际接口获取图片，再导入文件。默认严格检查尺寸；留白适配、裁剪和覆盖须显式指定。执行结果只表示文件可用，仍需按写作规则检查图片内容。

公众号凭证与平台、视角放在同一套项目配置中：`.env.example` 是占位模板，真实值写在本地 `.env`。

```bash
python3 openwrite.py setup   # 复制 .env.example 为 .env，已存在则不覆盖
```

然后编辑 `.env`：

```dotenv
WeChatAppID=wx1234567890abcdef
WeChatAppSecret=你的_appsecret
WeChatAuthor=你的作者名
```

`.env` 已被 `.gitignore` 忽略，`setup` 会将其权限设为 600；不要把真实密钥写入 `.env.example` 或提交到仓库。未配置凭证时 `publish` 会报错并给出上述指引，不再读取 `~/.wechat-publisher/config.json`。access_token 缓存仍在 `~/.wechat-publisher/token_cache.json`。

Skill 是项目级的，无需全局安装；仍需配置实际使用的图片来源或公众号等外部服务。发布器创建草稿，最终群发在微信后台操作。

## 开发验证

```bash
python3 -m unittest discover -s tests -v
```

旧版实时预览与批量排版脚本尚未适配当前排版器；项目入口使用当前核心转换脚本。

## 来源与许可证

本工程 fork 自 [BND-1/wechat_article_skills](https://github.com/BND-1/wechat_article_skills)，曾适配 Hermes Agent，现以 OpenWrite 为独立工程提供项目级通用 Agent 工作流。感谢上游作者。遵循 [MIT License](LICENSE)。
