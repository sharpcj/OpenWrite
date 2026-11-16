# Markdown 到 HTML 转换详细指南

本文档说明当前转换器的处理流程、技术实现与高级用法。核心脚本为 `scripts/markdown_to_html.py`：**纯手写解析器 + YAML 主题系统**，唯一外部依赖是 PyYAML（不使用 markdown / beautifulsoup4 / cssutils 等库）。

---

## 1. 转换流程概述

```
Markdown 文本
    ↓
[步骤1] 预格式化（可选，--no-preformat 跳过）
    ↓
[步骤2] 加载 YAML 主题 → 变量替换 → 元素样式表
    ↓
[步骤3] 手写解析器逐元素转 HTML（inline 样式）
    ↓
[步骤4] 追加 closing.md 文末区块（如存在）
    ↓
[步骤5] 文档包装（section 容器 + 全局字体/字号/行高）
    ↓
最终 HTML
    ↓
[步骤6] 微信代码块兼容转换（convert-code-blocks.py，项目入口自动执行）
```

复用入口：`convert_markdown(md_text, theme_name, overrides=None, preformat=True, closing_md=None)`，供 CLI、`batch_convert.py` 与 `preview_generator.py` 共用。

---

## 2. 各步骤详解

### 步骤1：预格式化（`_preformat_markdown`）

- 中英文之间自动补空格
- ASCII 引号转中文引号
- 压缩多余空行
- 对代码示例同样生效；需要保留原文时用 `--no-preformat`

### 步骤2：主题加载与样式构建

- `_load_theme(name)`：读取 `themes/<name>.yaml`（`name` / `description` / `variables` / `styles`）
- `_build_styles(theme, overrides)`：内置默认样式 + 主题 styles 合并，`{primary-color}` 等变量替换；`--color` / `--font-size` 作为 overrides 覆盖
- 主题缺失的元素沿用内置默认规则

### 步骤3：手写解析（`_md_to_html`）

逐元素精调，全部输出 inline 样式：

| 元素 | 处理要点 |
|------|---------|
| h1 | **第一个 H1 被移除**（公众号标题在后台单独填写） |
| h2-h4 | 按主题样式（色块/边框/留白） |
| 段落 | 字号、行高、字距、段间距 |
| 加粗/斜体 | 强调色可随主题 |
| 引用块 | 左边框 + 浅色背景 |
| 有序/无序列表 | 缩进与行距 |
| 分割线 | 主题化渐变或细线 |
| 图片 | `![alt](src)` → `<img>`，居中、max-width:100%；alt 含 `：` 时自动提取图注（figcaption） |
| 行内代码/代码块 | 行内码底色；代码块深色背景（微信发布前需步骤6转换） |
| 链接 | 主题色 + 下边框 |

### 步骤4：文末区块

输入文件同目录存在 `closing.md` 时，转换后追加到正文末尾（引导关注、免责声明等）。

### 步骤5：文档包装（`_wrap_document`）

输出 `<section>` 容器，携带全局 font-family / font-size / line-height / color / padding，并附注释提示标题需在后台填写。

### 步骤6：微信代码块兼容转换

微信编辑器不支持 `<pre><code>`。`scripts/convert-code-blocks.py` 将其转换为 `<div>` + `<br>` + `&nbsp;` 格式（微信唯一支持的代码块形态），保留缩进与换行。项目入口 `openwrite.py format` 自动执行，并检查 HTML 中不得残留 `<pre`。详见 [wechat-code-blocks.md](wechat-code-blocks.md)。

---

## 3. 高级用法

### 覆盖主色与字号

```bash
python scripts/markdown_to_html.py --input article.md --theme modern --color "#A93226" --font-size 15px
```

### 在 Python 中复用

```python
from markdown_to_html import convert_markdown

html = convert_markdown(md_text, "grace", overrides={"primary-color": "#6B4E9B"})
```

### 批量与预览

- `batch_convert.py`：目录级并发转换，共用同一主题
- `preview_generator.py`：标准库轮询监听修改时间，自动重转换 + 本地 HTTP 预览

两者均为底层能力，不享受项目七步状态检查。

---

## 4. 输出约束

- 所有样式 inline（微信不支持外部 CSS 与 JavaScript）
- 本地图片路径保留为 `<img src>`；项目发布链路自动上传，手工粘贴需在微信编辑器重新上传
- 表格建议 ≤4 列（移动端友好）

平台限制详见 [wechat-constraints.md](wechat-constraints.md)；主题定制详见 [theme-customization.md](theme-customization.md)。
