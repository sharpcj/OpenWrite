---
name: openwrite-images
description: 执行 OpenWrite 的配图需求，获取并校验本地图片。处理本地 ComfyUI、在线 AI 生图（fal.ai / 腾讯混元）、官方文档插图导入、免费图库（Pexels / Pixabay / Unsplash）、Agent 生图工具与已有图片的接入与结果交付；微信封面支持 Pillow 标题叠字。在项目需要生成、替换或导入封面和正文图片时使用，不负责正文写作与配图设计决策。
---

# OpenWrite 独立图片能力

## 职责与边界

读取文章目录中的 `image-requests.json`，取得符合需求的真实图片，交付本地 PNG 和 `image-results.json`。需求与结果格式见 [配图交接协议](../../docs/image-contract.md)。

不改写正文，不自行改变配图数量、色调、构图、画面文字和目标尺寸。需求不完整时，向项目流程说明缺项，由写作侧补充。三种写作视角（自媒体博主、技术作者、产品经理）共用本能力，不维护各自的后端副本。

## 图片来源与选择

四类来源，地址与密钥统一配置在项目根 `openwrite.yaml` 的 `image_sources` 节（见 [后端配置](references/api-configuration.md)），进程环境变量（如 `FAL_KEY`）可覆盖同名小写字段；模型档案、默认优先级与封面叠字版式在本目录 `config.json`：

| 来源 | 后端名 | 配置项（`image_sources` 下） |
|---|---|---|
| 本地/远程 ComfyUI | `comfyui` | `comfyui_server_url`（含端口，可逗号分隔多地址，本地优先） |
| 在线 AI 生图 | `fal` / `hunyuan` | `fal_key`（或别名 `fal_ai_api_key`）/ `tencent_tokenhub_api_key` |
| 免费图片资源站点 | `pexels` / `pixabay` / `unsplash` | `pexels_api_key` / `pixabay_api_key` / `unsplash_access_key` |
| 已有图片导入 | `file` | 无需配置；宿主生图输出、用户图片、**官方文档插图**均由 Agent 取得本地文件后导入 |

**按内容评估选源**由写作侧（Agent）完成：评估每张图适合什么来源，在需求中用 `preferred_sources` 声明偏好顺序；未声明时使用默认优先级：

- 正文配图（与官方文档内容强相关时优先官方插图）：官方文档插图（`file`）> 本地 ComfyUI > 免费图库 > 在线生图。
- 微信封面底图：本地 ComfyUI > 在线生图 > 免费图库。

`--backend auto`（默认）按上述顺序逐个尝试，失败自动回退下一来源，全部失败才报错；未配置密钥的来源自动跳过，不静默产生计费调用。官方文档插图需要搜索与内容判断，由 Agent 找到并下载原图，把本地路径写入需求 `source_file`、原始链接写入 `source_url`，模块以 `file` 方式导入并保留溯源信息。图库搜索需要需求提供 `keywords`。

其他规则：

- **文字密集型卡片（小红书图文）用 `html` 后端**：按需求中的 `card` 字段排版 HTML 并用 Playwright 精确截图，文字一字不差、版式可校验。不要用生图模型渲染需要精确文字的卡片。详见 [卡片渲染指南](references/card-rendering.md)。
- **微信封面用「底图 + 叠字」**：底图不渲染文字（`text` 置空），标题/副标题写在需求 `overlay` 对象中，由 `cover_text.py` 用 Pillow 精确排版叠加（默认底部渐变衬底 + 白色粗标题，可在 `overlay` 中覆盖位置/颜色/字号/字体）。`overlay.title` 必须是已确认的文章标题，控制器会校验一致性。
- 宿主 Agent 的生图工具：按其实际接口调用，将真实图片保存到本地后以 `file` 方式导入；不假设通用工具名、免费服务或统一参数。
- 流程图、板书和精确数据图优先使用可准确控制文字、连接关系和数据的绘图方式，之后导入；不要用不清晰的图代替精确表达。
- 保留 `gemini`、`dalle` 备用 API（密钥同样可配在 `image_sources` 的 `gemini_api_key` / `openai_api_key`），需用户已选择并配置；不参与 auto 默认优先级。Gemini 另需 `google-genai` SDK。

## 执行与交付

项目创作通过 `openwrite.py image` 执行，入口会检查七步工作流：只有当前处于 `cover` 或 `content` 才允许处理对应图片。先按 [工作流协议](../../docs/workflow.md) 完成前置步骤；图片执行成功不自动完成阶段，仍需视觉验收并提交。

在项目根目录执行：

```bash
# 默认 auto：按优先级多来源尝试并自动回退
.venv/bin/python openwrite.py image articles/my-topic --id cover

# 显式指定单一来源
.venv/bin/python openwrite.py image articles/my-topic --id cover --backend comfyui
.venv/bin/python openwrite.py image articles/my-topic --id cover --backend fal
.venv/bin/python openwrite.py image articles/my-topic --id diagram --backend pexels

# 导入宿主工具、官方文档插图或用户提供的真实图片
.venv/bin/python openwrite.py image articles/my-topic --id cover --backend file --source /path/to/image.png

# 明确允许留白适配或裁剪适配时
.venv/bin/python openwrite.py image articles/my-topic --id cover --backend file --source /path/to/image.jpg --fit contain
```

也可独立运行本目录的 `scripts/produce.py <文章目录> --id <标识> ...`。路径参数相对于调用时的工作目录。

- `--fit` 缺省时：auto 对生图后端用 `exact`、对图库/导入用 `cover`（等比裁剪）；显式单一后端用 `exact`。显式 `--fit` 对所有来源生效。`exact` 尺寸不匹配就报错，不默默改尺寸；`contain` 等比缩放白色留边。适配后必须复查文字、主体和构图。
- 已存在的图片默认不覆盖；确需替换时使用 `--overwrite`。失败时保留之前的图片和结果，不声称产生了新图。
- 成功时输出 JSON 并写入结果清单；`ready` 代表文件格式与尺寸已检查，`review: pending` 表示仍需写作侧进行视觉验收。结果记录实际使用的 `backend`、`fit`，以及来源溯源（`source_url` / `attribution` / `model`）；auto 回退时附 `attempts` 失败记录。
- 每次只执行一个 `id`，以便项目先完成封面，再按需处理正文配图。不要在同一文章目录并发执行，避免结果清单互相覆盖。

## ComfyUI 后端

`comfyui_gen.py` 负责工作流参数注入、提交任务和等待结果。服务地址来自 `openwrite.yaml` 的 `image_sources.comfyui_server_url`（进程环境变量 `COMFYUI_SERVER_URL` 可覆盖）；配置多个地址时本地（loopback）优先，逐个探测取第一个可达者。`produce.py` 再读取输出文件、校验真实图片并保存到文章目录。后端输出目录（环境变量 `COMFYUI_OUTPUT_DIR` 或 config.json 的 `comfyui_output_dir`）需在当前机器可访问；远程服务没有共享输出目录时，不能把虚构的本地路径当作图片。

需要图中渲染中文时优先 `z-image`，否则使用 `flux2`。可通过 `--profile` 显式覆盖；默认规则来自配置。需求执行入口仅用 `text` 字段判断画面是否要渲染中文，不把中文构图说明误当作画面文字。模型与工作流细节只在本能力维护，见 [模型档案指南](references/comfyui-profiles.md) 和 [后端配置](references/api-configuration.md)。

缺少可用来源、实际文件不可读、尺寸不符或图片损坏时报告失败；不生成占位图片来假装完成。

## 微信封面三维样式

微信任务可保存 `cover_style`，分别指定版式、视觉风格和色调。执行器只读取任务快照，统一解析为有效需求及其指纹；不重新读取全局样式改变已有任务。左文右图同时约束底图构图与实际文字排版区域，文字不扩展到右侧主体区域，底图主体位置仍需看图验收。配置、任务覆盖与自定义方式见 [封面样式](../../docs/cover-style.md)。
