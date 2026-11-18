# OpenWrite 配图来源配置

服务地址与 API 密钥统一配置在**项目根 `openwrite.yaml` 的 `image_sources` 节**（Git 忽略，权限 600；由 `.venv/bin/python openwrite.py setup` 从 `openwrite.example.yaml` 复制生成）。进程环境变量（如 `FAL_KEY`）可覆盖同名 YAML 字段（字段名为键的小写形式）。模型档案、工作流模板、默认来源优先级与封面叠字版式在 `skills/openwrite-images/config.json`（被 Git 跟踪，不放密钥）。

## 配置项一览

```yaml
image_sources:
  # ComfyUI 服务地址（含端口），本地或远程均可。
  # 多个地址用逗号分隔，本地（loopback）优先，逐个探测取第一个可达者。
  # 缺省默认 http://localhost:8188；config.json 的旧 comfyui_url 仍兼容读取。
  comfyui_server_url: http://localhost:6677

  # 在线 AI 生图：fal.ai（FLUX / Recraft 等，queue API）
  # 获取：https://fal.ai/dashboard/keys ；两个键任填其一（别名关系）。
  fal_key: ""
  fal_ai_api_key: ""

  # 在线 AI 生图：腾讯混元 TokenHub（Bearer token）
  # 获取：https://console.cloud.tencent.com/tokenhub
  # 默认模型 hy-image-v3.5-preview（同步接口，支持精确 size，最高 4K）。
  tencent_tokenhub_api_key: ""

  # 免费图片资源站点（搜索 + 下载，结果记录署名与出处）
  pexels_api_key: ""        # https://www.pexels.com/api/
  pixabay_api_key: ""       # https://pixabay.com/api/docs/
  unsplash_access_key: ""   # https://unsplash.com/developers
```

`doctor` 会列出各来源的配置状态（不显示密钥值、不联网）。未配置密钥的来源在 auto 模式下自动跳过；显式指定时报告缺少的配置项。

## 本地 ComfyUI

```bash
bash scripts/check_comfyui.sh          # 探测 openwrite.yaml 配置的地址（多地址逐个探测）
python3 scripts/comfyui_gen.py --prompt "封面提示词" --profile z-image --width 1024 --height 432
```

输出目录由 `COMFYUI_OUTPUT_DIR`（进程环境变量或 `image_sources.comfyui_output_dir`）或 config.json 的 `comfyui_output_dir` 指定，必须对应本机实际可访问的 ComfyUI 输出位置。图中需要渲染汉字时使用 `z-image`，其他情况使用 `flux2`；实际目标尺寸由写作侧需求指定。

## 在线 AI 生图

- **fal.ai**：`fal` 后端走 queue API（提交 → 轮询 → 取图），默认模型 `fal-ai/flux/dev`，可在 config.json `online_models.fal` 改为 Recraft 等模型（如 `fal-ai/recraft/v3/text-to-image`）。尺寸按 32 像素对齐，最终由 produce 校验/适配到需求尺寸。
- **腾讯混元**：`hunyuan` 后端调用 TokenHub 同步生图接口 `https://tokenhub.tencentmaas.com/v1/wand/hunyuan-image/v35-generation`，默认模型 `hy-image-v3.5-preview`（config.json `online_models.hunyuan` 可改）。需求尺寸超出模型约束时按比例缩放到合法范围生成，再适配回需求尺寸。返回的临时 URL（12 小时有效）立即下载转存。

两者都只在配置了密钥时参与 auto 回退；调用失败（限流/审核拦截等）如实报告并回退下一来源。

## 免费图片资源站点

`pexels` / `pixabay` / `unsplash` 后端按需求 `keywords` 搜索，优先选择分辨率足够且宽高比接近目标的图片下载；结果写入 `source_url`（作品页）与 `attribution`（作者署名）。Unsplash 按其 API 规范触发 download 跟踪端点。auto 模式对图库图片默认 `--fit cover`（等比裁剪到需求尺寸），验收时复查主体与构图。

## 官方文档插图与宿主生图

没有独立后端：由 Agent 搜索官方文档、判断插图与内容的相关性、下载原图到本地，把路径写入需求 `source_file`、原始链接写入 `source_url`（可选 `attribution`），以 `file` 方式导入。宿主 Agent 生图工具的输出同样以 `file` 导入。正文配图默认优先级中 `file` 居首，即体现"官方插图优先"。

## 备用直连 API

`scripts/generate_image.py` 保留 Gemini / DALL-E 直连方式，密钥同样可配在 `image_sources`（`gemini_api_key`、`openai_api_key`；进程环境变量 `GEMINI_API_KEY` / `GOOGLE_API_KEY`、`OPENAI_API_KEY` 可覆盖）：

```bash
python3 scripts/generate_image.py --prompt "提示词" --api gemini --output cover.png
python3 scripts/generate_image.py --prompt "提示词" --api dalle --quality hd --size 1792x1024 --output cover.png
```

不要将真实密钥提交到仓库。第三方 API 的模型可用性及参数以实际后端为准。

## 封面叠字（微信）

微信封面 = 无字底图 + Pillow 精确叠字。底图来源优先级：ComfyUI > 在线生图 > 免费图库；`overlay.title` 使用已确认标题，`subtitle` 可选。版式默认值在 config.json `cover_text`（字体候选、位置、颜色、衬底、字号比例），需求 `overlay` 可逐项覆盖；`overlay.font` 可指定本机字体文件。没有可用中文字体时报错并提示配置，不静默降级。
