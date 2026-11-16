# 卡片渲染指南（html 后端）

小红书图文的卡片是**文字密集型信息图**，不是插画。标题、要点、数据必须一字不差，因此用 HTML + CSS 排版、Playwright 精确截图，而不是交给生图模型。

模板与样式由 OpenWrite 自行编写（MIT），不复制 AGPL 项目代码。

## 何时用哪个后端

| 内容类型 | 后端 |
|---|---|
| 卡片、要点页、封面标题、数据/清单 | `html` |
| 照片、插画、氛围图、产品实拍 | `comfyui` / 宿主生图工具 / `file` |
| 用户提供的截图或图片 | `file` |

同一篇笔记可以混用：卡片用 `html`，照片素材用 `file` 导入，两者都走同一套尺寸校验与视觉验收。

## 调用方式

```bash
# 在项目根目录执行；当前步骤必须是 cover 或 content
python3 openwrite.py image articles/<名称> --id cover --backend html
python3 openwrite.py image articles/<名称> --id page1 --backend html
```

`html` 后端不需要 `--source`，也不使用 `--profile`；渲染输入来自需求中的 `card` 字段。

## 需求中的 card 字段

```json
{
  "id": "page1", "role": "content", "output": "xhs-02-why.png",
  "width": 1080, "height": 1440, "order": 2,
  "prompt": "解释答错的三个原因",
  "card": {
    "layout": "bullets",
    "theme": "indigo",
    "title": "为什么它会答错",
    "subtitle": "三个常见原因",
    "bullets": ["模型知识有截止时间", "缺少你的私有资料", "没有引用约束"],
    "footer": "OpenWrite 实测"
  },
  "text": ["为什么它会答错"],
  "acceptance": ["文字与卡片稿一致", "版式不溢出", "字号可读"]
}
```

- `layout`：`cover`（大标题 + 副标题 + 要点）、`bullets`（标题 + 要点列表）、`quote`（标题 + 引文）。
- `theme`：`default`（简约灰）、`indigo`（靛蓝）、`forest`（森林墨）、`kraft`（牛皮纸）、`midnight`（午夜墨）。**整套卡片保持同一主题**。
- `title` 必填；`bullets` 版式需要 `subtitle` 或 `bullets` 之一，避免产出空白卡片。
- `order`：组图上传顺序，封面固定第 1，内容卡片从 2 开始且不可重复。
- `safe_area`：可选，覆盖默认边距（默认 side 84 / top 96 / bottom 104，落在平台安全区范围内）。

`card` 内容参与需求指纹：改卡片文案 → 指纹变化 → 已渲染图片失效 → 必须重渲。`cards.md` 另纳入第三步指纹，改卡片稿会让正文及下游一起过期。

## 渲染与校验流程

1. 按 `card` 生成单文件 HTML（内容经转义，尺寸即需求宽高）。
2. Playwright 打开页面，viewport 为需求尺寸，`device_scale_factor=2`。
3. 等待字体就绪后，用**真实 DOM 测量**校验：
   - 内容纵向/横向溢出安全区
   - 任何文本字号低于可读下限（24px）
   - 内容 bounding box 超出安全区边距
4. 校验不通过即报错，不产出图片；通过则截图。
5. 用 Pillow 降采样到需求精确尺寸并保存 PNG。

校验只保证**版式成立**，不保证内容正确。文字是否与卡片稿一致、数据是否真实、结论是否与文案相符，仍须实际看图验收后提交 `--reviewed --note`。

## 依赖

```bash
python3 -m pip install -r requirements.txt   # 含 playwright
python3 -m playwright install chromium       # 一次性下载浏览器
python3 openwrite.py doctor                  # 显示「卡片渲染：OK」
```

浏览器下载后可离线使用。`doctor` 只做本地检查，不会自动下载。缺少依赖时说明缺口并保留卡片稿与需求，不伪造图片。

## 动态张数

张数由内容决定，不为凑数加页，也不把多个观点挤进一页。写作侧按「一页一个观点」给出卡片稿，渲染期校验会拦住挤爆的页面；此时应拆页或精简文案，而不是缩小字号硬塞。

平台单篇图片上限尚未取得权威来源，已记入注册表 `unverified: ['max_images']`，不凭印象写死。

## 独立运行

```bash
python3 skills/openwrite-images/scripts/render_card.py <单需求JSON> --output card.png
```

独立运行不提供工作流阶段检查；项目创作统一走 `openwrite.py image`。
