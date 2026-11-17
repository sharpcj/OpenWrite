# 七步创作工作流

项目入口用 `workflow/workflow.json` 保存进度并检查阶段产物。Agent 完成当前阶段的工作后提交结果，由代码检查并推进。它不自动调用大模型，也不自动判断论据或图片是否足够好。

整体分三个模块：**下发需求 → 写作 → 发布**。写作即下面的七步，最终交付可发布产物；发布必须由用户明确确认。

固定顺序：**搜索资料 → 分析资料 → 写正文 → 生成封面 → 按需生成正文配图 → 生成 Markdown → 生成可发布交付件**。

顺序与门禁平台中立，产物形态按平台分派（注册表 `platforms.py`）。第七步标签全平台统一为「生成可发布交付件」（注册表 `format_label`），产物形态仍随平台变化。平台差异详见 [平台适配器契约](platforms.md)。

## 最小阶段协议

| 步骤标识 | 必需产物 | 代码检查 |
|---|---|---|
| `search` | `process/sources.json` | 至少一个来源；有标题、实际提取内容及 URL，或明确为用户资料 |
| `analysis` | `process/analysis.md` | 有实际内容，通过 `source:<id>` 关联已有来源 |
| `draft` | `process/outline.md`、`workflow/outline.json`、`process/draft.md`（小红书另需 `process/cards.md`） | 标题与大纲已获用户确认；正文不只是标题、不嵌图；H1 与已确认标题一致 |
| `cover` | 封面需求、图片执行结果、封面文件 | 需求指纹一致；图片可解码、格式与尺寸正确；提交验收记录 |
| `content` | `workflow/content-images.json`，以及需要的正文配图 | 明确是否需要；决策与清单一致；需要的图片均有效、已验收；微信校验插入锚点，小红书校验 `order` |
| `markdown` | 程序生成的 `article.md` / `note.md` | 前五步有效；微信插图整合，小红书只整合文案 |
| `format` | 微信 `article.html`；小红书卡片组 + 清单 | 前六步有效；可发布性检查通过；清单记录元数据与全部产物指纹 |

`process/brief.md` 仍保存主题、受众、额外约束和过程备注。`workflow/workflow.json` 由命令管理，不由 Agent 直接编辑来跳过步骤。每篇文章按单一任务顺序执行，不并发更新状态。

第六步由 `workflow finalize` 完成，第七步由 `openwrite.py format` 完成；两者都不能用 `workflow complete --step` 提交。

## 初始化与查看

新任务及 `workflow init` 按 [平台与视角规则](task-selection.md) 只读取本地 `.env`（`.env.example` 仅是 `setup` 用的模板）；提示词明确指定值由 Agent 转为参数。默认微信与自媒体博主。已保存任务继续沿用原选择。小红书已完整接入（写作、卡片产物与发布）；任务按图文形态推进，不会套用微信长文规则。

```bash
python3 openwrite.py new rag-guide --title "RAG 入门" --type tech
python3 openwrite.py workflow status articles/rag-guide
```

`new` 创建需求文件、空来源清单、分析与正文标题草稿及工作流状态，**不会提前创建最终 `article.md`**。更换 Agent 或会话后，先运行 `status` 并阅读当前产物。

已有文章目录可以运行 `workflow init <目录>`。它只初始化状态，所有步骤仍需按顺序提交；不会因为文件已经存在就自动认可完成。将正文准备为 `process/draft.md`，不要以旧文件名或修改时间跳过步骤。

## 工作区目录分层

根目录只放可交付产物（微信 `article.html` / `article.md` / `cover.png` 与正文配图；小红书 `note.md` 与 `xhs-*.png`）；`process/` 放中间产物（brief、sources、analysis、outline 讨论稿、draft、cards、closing）；`workflow/` 放框架物件（workflow.json、outline.json、image-requests/results、content-images、publish-manifest、publish-record）。路径统一由 `layout.py` 派生：读侧 `existing()` 无副作用（兼容旧平铺），写侧 `path()` 自动建目录。旧目录用 `workflow migrate <目录>` 升级；指纹为内容哈希，迁移不使验收失效。下文裸文件名按此分层解析。

## 前三步

搜索后保存 `process/sources.json`：

```json
{
  "version": 1,
  "sources": [
    {
      "id": "s1",
      "title": "官方资料标题",
      "url": "https://example.com/docs",
      "content": "实际提取的相关内容或摘要，不能只有一个链接"
    }
  ]
}
```

用户提供的资料可用 `"kind": "user"`，不要求 URL，但仍需标题和实际内容。代码检查格式，来源真实性与搜索充分性由执行者核实。

分析写入 `process/analysis.md`，例如“source:s1 支持……；尚未确认……；文章核心观点为……”。

```bash
python3 openwrite.py workflow complete articles/rag-guide --step search
python3 openwrite.py workflow complete articles/rag-guide --step analysis
```

不允许跳步、重复提交已完成步骤，或以只有标题的文件通过检查。

## 标题与大纲检查点

分析完成后、写正文之前，必须取得用户对标题与大纲的确认（除非已授权跳过）。这是 `draft` 步的前置条件，不单独设步骤。

1. 给出三个备选标题，风格标注至少包含 `激进悬念`（激进、有悬念、吸引点击）与 `客观中性`（相对客观中性），第三个默认 `利益实用`（读完能得到什么）。
2. 同时给出大纲，请用户选定标题（可自定义）并确认大纲。
3. 用户可反复提出修改意见；每轮更新 `process/outline.md`，未确认前不生成正文全文。
4. 确认后写入 `workflow/outline.json`，再写 `process/draft.md` 并提交 `--step draft`。

`process/outline.md` 示例：

```markdown
# 标题与大纲

## 备选标题
1. 激进悬念：知识库没用对，AI 一直在瞎编？
2. 客观中性：RAG 如何提升 AI 回答的准确性
3. 利益实用：三步让你的 AI 答得更准

## 大纲
- 开头：一个答非所问的真实场景
- 为什么会答错：模型知识的边界
- RAG 做了什么：检索 + 生成
- 落地建议与常见坑

## 讨论与确认
- 第 1 轮：用户认为大纲第 3 节太技术，要求改为效果对比
- 第 2 轮：用户选定标题 2，同意修改后的大纲
```

`workflow/outline.json` 示例：

```json
{
  "version": 1,
  "candidates": [
    {"title": "知识库没用对，AI 一直在瞎编？", "style": "激进悬念"},
    {"title": "RAG 如何提升 AI 回答的准确性", "style": "客观中性"},
    {"title": "三步让你的 AI 答得更准", "style": "利益实用"}
  ],
  "chosen_title": "RAG 如何提升 AI 回答的准确性",
  "title_source": "candidate",
  "approved": true,
  "outline_hash": "outline.md 的 SHA-256"
}
```

代码检查：候选不少于三个且包含两种必需风格；`chosen_title` 非空；`title_source` 为 `candidate`（必须在候选中）或 `user`（用户自定义）；`approved` 为 `true`；`outline_hash` 与当前 `process/outline.md` 一致；`process/draft.md` 的 H1 等于 `chosen_title`。代码只校验结构，标题好坏与大纲质量由用户判断。

提交 `draft` 时选定标题会同步到 `workflow/workflow.json` 的 `title`，供排版与发布使用。确认后修改 `process/outline.md` 会使确认失效，并让已完成的正文及下游过期。

是否启用由 `.env` 的 `OutlineApproval` 控制（默认 `true`）；用户明确授权跳过时可传 `new --skip-outline` 或 `workflow init --skip-outline`。选择在创建任务时写入 `outline_approval`，之后修改配置不影响已有任务。旧任务没有该字段时不追加此要求。

## 封面与正文配图

写作 Skill 按 [配图交接协议](image-contract.md) 定义需求。项目图片命令在 `cover` 阶段只允许处理封面，在 `content` 阶段只允许处理正文图片；独立图片能力的后端实现保持解耦。

```bash
# 当前步骤必须是 cover；也可以用已配置的其他后端
python3 openwrite.py image articles/rag-guide --id cover --backend file --source /path/to/cover.png
# 实际看图并确认主题、文字、色调、构图等符合要求后提交
python3 openwrite.py workflow complete articles/rag-guide --step cover --reviewed --note "已检查标题、构图和正文主题一致"
```

正文配图必须明确做出决策。无须配图时，保存 `workflow/content-images.json`：

```json
{"needed": false, "reason": "正文以观点论述为主，文字已经足够清楚"}
```

同时 `workflow/image-requests.json` 不应有正文图片项，再提交：

```bash
python3 openwrite.py workflow complete articles/rag-guide --step content
```

需要配图时，改为 `needed: true` 并说明理由，将正文图片需求追加到清单，逐项获取后提交 `--reviewed --note "验收说明"`。`placement` 必须完整且唯一地匹配 `process/draft.md` 中的某一行标题或段落（也可用完整的多行段落）；程序在它后面插图。不要使用“第二部分附近”这样的模糊描述。

`--reviewed` 是执行者实际完成视觉检查后的确认，可以由有看图能力的 Agent 提交，也可由用户确认后记录。它不意味着必须每一步询问用户，也不是机器自动判断画面正确。无看图能力时不得伪造验收，应挂起该步交用户确认。

封面和正文图片分别记录指纹，追加正文图片需求不会使已完成的封面无故失效。

## 生成 Markdown 与可发布产物

```bash
python3 openwrite.py workflow finalize articles/rag-guide
python3 openwrite.py format articles/rag-guide --theme default
# 保留正文和代码的原始引号、间距可加 --no-preformat
```

`finalize` 是第六步：根据 `process/draft.md` 和正文图片插入位置生成 `article.md`；封面不写入正文。最终文件由程序整合，不让 Agent 另写一份与草稿脱节的正文。

`format` 是第七步。微信：转换 HTML、执行微信代码块兼容转换，然后做**可发布性检查**——标题不超过 64 字符 / 192 字节、作者不超过 20 字节、摘要不超过 120 字节、封面存在且为 PNG 且小于 2MB、HTML 非空、代码块已转换、正文引用的本地图片都存在。

小红书：卡片已在第 4/5 步由 `html` 后端渲染，第七步**只组装与校验**——确定卡片顺序（封面第 1，内容按 `order`）、标题不超过 20 字、逐张校验 PNG 与 1080×1440 尺寸、核对 `note.md` 标题与文案、解析话题。

任一检查不通过即报错，保留上一次成功的产物，不推进状态。

检查通过后写入 `workflow/publish-manifest.json` 并自动完成第七步：

```json
{
  "version": 1,
  "platform": "wechat",
  "title": "RAG 如何提升 AI 回答的准确性",
  "author": "来自 .env 的 WeChatAuthor",
  "digest": "",
  "theme": "default",
  "preformat": true,
  "cover": "cover.png",
  "content_images": ["structure.png"],
  "files": {"article.md": "SHA-256", "article.html": "SHA-256", "cover.png": "SHA-256"},
  "checks": {"title_chars": 18, "cover_bytes": 204800, "html_chars": 12000, "local_images": 1}
}
```

七步完成即代表产物可发布。换主题重排版可直接再运行 `format`，它替换第七步记录而不是追加；上游产物变化时仍需先 `reset`。

## 发布

```bash
# 只有用户明确确认发布时执行
python3 openwrite.py publish articles/rag-guide
```

`publish` 要求七步完成，且 `workflow/publish-manifest.json` 记录的指纹与当前产物完全一致；标题默认取清单中已确认的值，`--title` / `--author` / `--digest` 可显式覆盖。产物在确认后被修改时旧确认失效，必须重新排版并重新取得用户确认。微信凭证来自项目 `.env`，未配置时在调用微信 API 之前报错。

**小红书发布**：七步完成后 `publish` 按清单顺序上传组图与笔记文案，默认「仅自己可见」；公开需用户显式 `--public`，可先 `--dry-run` 预演（仅本地校验，不登录不发布）。凭证为 `.env` 的 `XhsCreatorCookie`，未配置或失效时在发布前报错。只有观察到站点成功信号才报告已发布；失败保留截图，可修正后重试。

**发布记录**：发布成功（发布脚本退出码 0）后入口写入 `workflow/publish-record.json`（平台、标题、可见性、时间戳）；微信可见性记为 `draft`（草稿箱），小红书为 `private` / `public`；`--dry-run` 不写记录。看板右栏的「已发布」节点只以该记录为依据，产物过期不抹掉历史发布事实。

## 返工与恢复

```bash
python3 openwrite.py workflow reset articles/rag-guide --from draft
# 修改 outline.md / draft.md，重新取得确认后从 draft 阶段逐步完成
python3 openwrite.py workflow complete articles/rag-guide --step draft
```

退回会清除该阶段及其下游完成状态，保留产物文件，不删除图片或正文。可以复用仍符合新需求的图片，但必须重新检查并提交图片阶段验收；需要重新取得图片时使用图片入口的 `--overwrite`。只重排版时 `reset --from format` 即可，不影响正文与已验收图片。

每次推进、获取图片、排版或上传时都会检查已完成产物指纹。上游内容变化、图片丢失或损坏、需求变更都会阻止继续，并指出最早需要退回的步骤。中断或失败后，重新运行 `status` 即可恢复，不必重新创建文章目录。

这是项目入口内的顺序约束，不是权限沙箱。底层能力脚本可独立使用；Agent 仍拥有直接修改文件和执行命令的权限。项目创作任务统一使用 `openwrite.py`，不通过直接调用底层脚本绕过状态检查。
