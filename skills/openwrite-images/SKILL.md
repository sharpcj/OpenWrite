---
name: openwrite-images
description: 执行 OpenWrite 的配图需求，获取并校验本地图片。处理 ComfyUI、Agent 生图工具、已有图片和备用 API 的接入与结果交付；在项目需要生成、替换或导入封面和正文图片时使用，不负责正文写作与配图设计决策。
---

# OpenWrite 独立图片能力

## 职责与边界

读取文章目录中的 `image-requests.json`，取得符合需求的真实图片，交付本地 PNG 和 `image-results.json`。需求与结果格式见 [配图交接协议](../../docs/image-contract.md)。

不改写正文，不自行改变配图数量、色调、构图、画面文字和目标尺寸。需求不完整时，向项目流程说明缺项，由写作侧补充。三种写作视角（自媒体博主、技术作者、产品经理）共用本能力，不维护各自的后端副本。

## 图片来源选择

- 默认优先使用配置好的本地 ComfyUI。配置唯一位置为本目录 `config.json`，支持 `COMFYUI_URL`、`COMFYUI_OUTPUT_DIR`、`COMFYUI_PROFILE` 覆盖。
- ComfyUI 不可达时说明情况，让用户选择手动启动服务或使用已配置的其他来源，不静默切换计费后端。用户已经指定来源时直接遵循。
- 宿主 Agent 的生图工具：按其实际接口调用，将真实图片保存到本地后以 `file` 方式导入；不假设通用工具名、免费服务或统一参数。
- 用户提供图片、截图、摄影、绘图软件输出：同样以 `file` 方式导入。确认来源可用于本次文章。
- 流程图、板书和精确数据图优先使用可准确控制文字、连接关系和数据的绘图方式，之后导入；不要用不清晰的图代替精确表达。
- 保留 `gemini`、`dalle` 备用 API，需用户已选择并配置对应密钥；Gemini 另需 `google-genai` SDK。接口与模型可用性以实际后端为准。

## 执行与交付

项目创作通过 `openwrite.py image` 执行，入口会检查七步工作流：只有当前处于 `cover` 或 `content` 才允许处理对应图片。先按 [工作流协议](../../docs/workflow.md) 完成前置步骤；图片执行成功不自动完成阶段，仍需视觉验收并提交。

在项目根目录执行：

```bash
# 默认本地 ComfyUI，依据需求选择工作流
python3 openwrite.py image articles/my-topic --id cover --backend comfyui

# 导入宿主工具、绘图软件或用户提供的真实图片
python3 openwrite.py image articles/my-topic --id cover --backend file --source /path/to/image.png

# 明确允许留白适配或裁剪适配时
python3 openwrite.py image articles/my-topic --id cover --backend file --source /path/to/image.jpg --fit contain

# 已明确选择并配置的备用 API；尺寸适配需显式指定
python3 openwrite.py image articles/my-topic --id cover --backend dalle --fit cover
```

也可独立运行本目录的 `scripts/produce.py <文章目录> --id <标识> ...`。路径参数相对于调用时的工作目录。

- `--fit exact` 为默认：实际尺寸不匹配就报错，不默默改尺寸。
- `--fit contain`：等比缩放，白色留边；`--fit cover`：等比缩放并裁剪。适配后必须复查文字、主体和构图。
- 已存在的图片默认不覆盖；确需替换时使用 `--overwrite`。失败时保留之前的图片和结果，不声称产生了新图。
- 成功时输出 JSON 并写入结果清单；`ready` 代表文件格式与尺寸已检查，`review: pending` 表示仍需写作侧进行视觉验收。
- 每次只执行一个 `id`，以便项目先完成封面，再按需处理正文配图。不要在同一文章目录并发执行，避免结果清单互相覆盖。

## ComfyUI 后端

`comfyui_gen.py` 负责工作流参数注入、提交任务和等待结果。`produce.py` 再读取输出文件、校验真实图片并保存到文章目录。后端输出目录需在当前机器可访问；远程服务没有共享输出目录时，不能把虚构的本地路径当作图片。

需要图中渲染中文时优先 `z-image`，否则使用 `flux2`。可通过 `--profile` 显式覆盖；默认规则来自配置。需求执行入口仅用 `text` 字段判断画面是否要渲染中文，不把中文构图说明误当作画面文字。模型与工作流细节只在本能力维护，见 [模型档案指南](references/comfyui-profiles.md) 和 [后端配置](references/api-configuration.md)。

缺少可用来源、实际文件不可读、尺寸不符或图片损坏时报告失败；不生成占位图片来假装完成。
