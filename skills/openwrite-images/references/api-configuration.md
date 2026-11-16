# OpenWrite 配图生成配置

## 首选：本地 ComfyUI

在本图片能力目录下执行：

```bash
bash scripts/check_comfyui.sh
python3 scripts/comfyui_gen.py --prompt "封面提示词" --profile z-image --width 1024 --height 432
```

服务地址、输出目录和模型档案见本图片能力的 `config.json`，可用 `COMFYUI_URL`、`COMFYUI_OUTPUT_DIR`、`COMFYUI_PROFILE` 覆盖。检测脚本的地址通过 `COMFYUI_URL` 指定；修改配置中的地址时请同步设置该变量。

图中需要渲染汉字时使用 `z-image`，其他情况使用 `flux2`。实际目标尺寸由写作侧需求指定。脚本输出 ComfyUI 图片路径；输出目录必须对应实际可访问的 ComfyUI 输出位置。将图片复制到文章目录，封面命名为 `cover.png`，不要嵌入正文。

## 备选：当前 Agent 的生图能力

ComfyUI 不可用时，先说明情况，由用户选择手动启动服务或使用宿主已提供且已配置的生图工具。不要假设所有 Agent 都有同名工具、相同参数、免费额度或免密钥服务。

按实际工具接口传入提示词与目标尺寸；如尺寸不支持，选择接近比例并说明。将返回图片保存到文章目录，确认文件存在后再引用。若只有 URL，按宿主允许的方式获取本地图片用于封面上传。

没有可用生图能力时，提供提示词与待生成清单，明确图片未生成。

## 可选：直接调用第三方 API

`scripts/generate_image.py` 保留 Gemini / DALL-E 直连方式，需自行配置对应后端和密钥：

```bash
export GEMINI_API_KEY="your-gemini-api-key"
# 或配置 OPENAI_API_KEY
python3 scripts/generate_image.py --prompt "提示词" --api gemini --output cover.png
python3 scripts/generate_image.py --prompt "提示词" --api dalle --quality hd --size 1792x1024 --output cover.png
```

不要将真实密钥提交到仓库。第三方 API 的模型可用性及参数以实际后端为准。

## 中文文字质量

图片生成后检查中文字形与可读性。减少画面文字、缩短标题；必要时生成无字背景，再使用软件排字。
