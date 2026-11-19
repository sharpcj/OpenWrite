# 配图交接协议

本协议连接写作规则与独立图片能力。写作 Skill 负责说明要什么图、评估适合的来源并如何验收；项目流程负责提交需求、取得图片、交回验收。图片能力不修改正文，也不决定是否需要配图。

## 来源评估与优先级

图片来源分四类：本地/远程 ComfyUI、在线 AI 生图（fal.ai / 腾讯混元 TokenHub）、官方文档插图、免费图库（Pexels / Pixabay / Unsplash）。地址与密钥配置在项目根 `openwrite.yaml` 的 `image_sources` 节，见 [后端配置](../skills/openwrite-images/references/api-configuration.md)。

写作侧按内容评估每张图适合的来源，用 `preferred_sources` 声明偏好顺序；未声明时按默认优先级执行，`--backend auto` 逐个尝试、失败自动回退：

| 场景 | 默认优先级 |
|---|---|
| 正文配图（与官方文档内容强相关） | 官方文档插图 > 本地 ComfyUI > 免费图库 > 在线生图 |
| 微信封面底图 | 本地 ComfyUI > 在线生图 > 免费图库 |

官方文档插图需要搜索与内容判断，由 Agent 找到并下载原图，把本地路径写入 `source_file`、原始链接写入 `source_url`，图片能力以 `file` 方式导入（默认优先级中 `file` 居首即体现官方插图优先）。图库搜索需要 `keywords`。未配置密钥的来源自动跳过，不静默计费。

**微信封面为「底图 + 标题叠字」**：底图不渲染文字（`text` 置空），大标题/副标题/小标语写入 `overlay`，由图片能力用 Pillow 精确排版叠加。`overlay.title` 是封面大标题，**可短于文章标题**（用更短的营销标题，细节交给副标题/标语），不再强制与文章标题一致；`subtitle`、`tagline` 可选。

## 配图需求：image-requests.json

文件放在文章目录的 `workflow/` 子目录（框架物件层，见 [工作流分层](workflow.md#工作区目录分层)）。三种写作视角共用格式，不包含模型、API、凭证或服务地址；来源偏好（`preferred_sources`）属于设计决策，可以声明。

```json
{
  "version": 1,
  "images": [
    {
      "id": "cover",
      "role": "cover",
      "output": "cover.png",
      "width": 1024,
      "height": 432,
      "type": "concept",
      "style": "简约科技插画",
      "palette": ["#1a1f5c", "#7c3aed", "#ffffff"],
      "composition": "右侧用知识卡片与光线表达检索；左下留白给标题叠字",
      "text": [],
      "prompt": "用连接知识卡片的光线表达检索增强，主题明确，避免无关机器人，画面不出现任何文字",
      "overlay": {"title": "让 AI 找对资料", "subtitle": "检索增强实战指南", "tagline": "说清想法，看着预览改", "position": "bottom-left"},
      "preferred_sources": ["comfyui", "fal", "hunyuan", "pexels", "pixabay", "unsplash"],
      "placement": "cover-only",
      "alt": "文章封面",
      "acceptance": ["大标题清晰可读", "主题与正文一致", "画面只保留一个焦点"]
    }
  ]
}
```

每篇完整任务固定一项封面需求。微信正文配图按需追加 `role: content` 项，也可以没有；结构图是可选正文配图。微信正文配图的 `placement` 应完整且唯一地匹配 `process/draft.md` 中的标题行或段落文本，程序在该位置之后插入图片，`alt` 应说明图的内容。

**平台差异**（详见 [平台适配器契约](platforms.md)）：

| 项 | 微信 | 小红书 |
|---|---|---|
| 封面文件名 | `cover.png` | `xhs-01-cover.png`（即组图首图） |
| 封面尺寸 | 1024×432 | 1080×1440（3:4） |
| 正文图尺寸 | 1024×768 | 1080×1440 |
| 正文图是否必需 | 可选，可为零张 | 必需，张数由内容动态决定 |
| 位置表达 | `placement` 匹配正文锚点 | `order` 整数（封面第 1，内容从 2 起，不重复） |
| 常用后端 | `comfyui` / `fal` / `hunyuan` / 图库 / `file`，封面另加 Pillow 叠字 | 卡片用 `html`，照片素材用 `file` |
| 第六步 | 插图整合为 `article.md` | 整合文案为 `note.md`，**不嵌图** |
| 第七步 | 排版渲染 HTML | 组装卡片顺序 + 校验 + 清单 |

小红书卡片需求额外带 `card` 字段（`layout` / `theme` / `title` / `subtitle` / `bullets` / `footer`），由 `html` 后端排版渲染；`card` 内容参与需求指纹，改文案即令已渲染卡片失效。见 [卡片渲染指南](../skills/openwrite-images/references/card-rendering.md)。

- `id`：唯一标识，仅字母、数字、下划线和连字符。
- `output`：文章同目录内唯一的 PNG 文件名，不带路径；封面文件名由平台注册表约定（微信 `cover.png`，小红书 `xhs-01-cover.png`）。
- `width`、`height`：目标像素尺寸。微信约定封面 1024×432、正文配图 1024×768；小红书统一 1080×1440。
- `prompt`：图片内容与表达目的。可以是自然语言设计说明，不是后端调用参数。
- `type`、`style`、`palette`、`composition`：画面类型、风格、配色及构图思路。
- `text`：画面需要出现的原文列表；无文字时用空列表。微信封面使用 `overlay` 叠字时 `text` 必须为空，避免文字重复。
- `overlay`：仅封面可用的叠字对象。`title` 必填（封面大标题，可短于文章标题）；`subtitle`（中副题）、`tagline`（小标语，弱化灰色小字）可选。**实际渲染哪些层次由封面样式的 `text.levels` 决定**，样式未声明的层次会被裁剪。`position`（`bottom-left` 等八个方位）、`color`、`tagline_color`、`font`、`font_size`、`subtitle_size`、`tagline_size`、`scrim` 可覆盖默认版式。与 `card` 互斥。科技样式另通过 `effect: tech-glow` 启用双层发光和左侧 smoothstep 暗层，支持独立副标题/标语字体、字色及光晕/暗层参数，见 [科技封面参数](cover-style.md#深色科技发光标题)。左文右图样式通过 `effect: warm-editorial` 启用无描边实心文字，支持独立字体与字色、明确换行、层间距及 `line_gap`，见 [暖色排版](cover-style.md#左文右图平滑渐变背景)；所有样式默认效果参数参与有效需求指纹。升级左文右图样式后旧结果会过期，需 reset cover 并重新验收；全幅单标题和科技样式不变。
- `preferred_sources`：可选，来源偏好顺序（`comfyui` / `file` / `fal` / `hunyuan` / `pexels` / `pixabay` / `unsplash` / `html` / `gemini` / `dalle`），不重复；缺省按场景默认优先级。
- `source_file`：可选，已有图片的本地路径（官方文档插图、宿主生图输出、用户图片），供 `file` 来源导入。宿主生图底图等中间图像文件应保存在 `process/`；被需求 `output` 或正文引用的成品图留根目录。
- `source_url`、`attribution`：可选，图片原始出处链接与署名/版权信息，随结果保留以便溯源。
- `keywords`：可选但图库来源必需，搜索关键词字符串列表。
- `acceptance`：可检查的设计与内容要求；数据图必须与正文的真实数据一致。

执行器校验标识、文件名、尺寸和字段格式。配图的主题、色调、构图、文字、数据与插入位置由写作侧补全并验收，不由执行器猜测。

## 图片结果：image-results.json

图片能力取得、解码并检查实际图片后，返回结果，例如：

```json
{
  "version": 1,
  "images": [
    {
      "id": "cover",
      "output": "cover.png",
      "backend": "comfyui",
      "width": 1024,
      "height": 432,
      "request_hash": "实际需求内容的 SHA-256",
      "status": "ready",
      "review": "pending",
      "fit": "exact",
      "model": "flux2",
      "source_url": "https://docs.example.com/figure.png",
      "attribution": "Example Official Docs",
      "attempts": [{"backend": "comfyui", "error": "…"}]
    }
  ]
}
```

`backend` 记录实际取得图片的来源；`source_url` / `attribution` / `model` / `query` 为可选溯源信息（官方插图出处、图库署名、生图模型等）；auto 回退时 `attempts` 记录此前失败的来源与原因。`ready` 只表示实际文件已取得且通过格式与尺寸校验，**不代表视觉验收通过**。写作侧仍需查看图片，核对文字、事实、色调、构图和正文相关性；实际查看图片后，通过项目工作流的 `complete --reviewed --note` 提交验收，控制器将图片及需求指纹与该阶段验收关联；细节也可补充到 `process/brief.md`。

需求发生变化后，之前的验收不再自动有效。项目流程需对照需求指纹及实际文件重新检查、取得或验收图片。不要仅凭文件名或旧的 `ready` 状态认定当前需求已完成。

## 七步流程中的交接

固定顺序不变：**搜索资料 → 分析资料 → 写正文 → 生成封面 → 按需生成正文配图 → 生成 Markdown → 排版并保存可发布产物**。

第 4 步由写作侧提交封面需求，项目流程调用独立图片能力，写作侧验收返回图片。第 5 步对每张必要正文配图执行同样交接。第 6 步运行 `workflow finalize`：微信把 `process/draft.md` 与已验收正文图片整合为 `article.md`（封面单独处理）；小红书整合文案为 `note.md`，卡片不嵌入文案。第 7 步 `format`：微信渲染 `article.html` 并检查本地图片齐备；小红书组装卡片顺序、逐张校验并写清单。两者都把产物指纹写入 `workflow/publish-manifest.json`。

缺少可用图片来源或验收未通过时，记录未完成事项，不把需求文件当作已生成的图片，也不声称整篇文章已完整交付。

阶段推进与返工规则见 [七步工作流](workflow.md)。

## 微信封面三维样式

项目 `openwrite.yaml` 中任务账号的封面版式、视觉风格、色调在创建任务时存入 `workflow.json.cover_style`。独立图片能力将该快照解析为有效需求，工作流使用同一有效需求校验指纹。写作侧应以快照为准，不在画面描述中写入冲突的风格和构图。左文右图底图留白，标题和关键词句通过 `overlay` 叠字，`text` 置空。原始需求文件保留，实际执行需求由解析器统一确定。详见 [封面样式](cover-style.md)。
