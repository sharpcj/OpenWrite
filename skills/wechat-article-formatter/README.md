# WeChat Article Formatter

将 Markdown 文章转换为适合微信公众号的美化 HTML（所有样式 inline），一键生成专业排版。

> **项目约定**：在 OpenWrite 中统一通过 `python3 openwrite.py format <文章目录>` 调用本能力（第七步，含状态校验、微信代码块转换与可发布性检查）。本文档介绍底层脚本的独立用法，不享受七步状态检查。Agent 执行指南见 [SKILL.md](SKILL.md)。

---

## ✨ 核心功能

- 📝 **Markdown 转 HTML** - 纯手写解析器，零外部 Markdown 依赖；支持 h1-h4、段落、加粗、斜体、引用、列表、分割线、图片、代码块等
- 🎨 **YAML 主题系统** - default（经典蓝）、grace（优雅紫）、modern（暖橙）、simple（极简黑），变量替换一键换色
- 💅 **inline 样式** - 微信编辑器兼容，直接粘贴
- 🔧 **微信代码块转换** - `<pre><code>` 转为微信唯一支持的 div+br+nbsp 格式
- ⚡ **批量转换** - 目录级并发转换
- 👀 **实时预览** - 标准库轮询监听，无额外依赖
- 🈶 **预格式化** - 中英文间距、引号规范化（`--no-preformat` 可保留原文）

---

## 🚀 快速开始

```bash
# 单篇转换（项目任务中由 openwrite.py format 自动调用）
python scripts/markdown_to_html.py --input article.md --theme default --preview

# 含代码块时执行微信兼容转换
python scripts/convert-code-blocks.py article.html article.html

# 批量转换
python scripts/batch_convert.py --input articles/ --theme grace --workers 8

# 实时预览（修改 Markdown 后刷新浏览器）
python scripts/preview_generator.py --input article.md --theme modern
```

---

## 🎨 内置主题

| 主题 | 风格 | 适用场景 |
|------|------|---------|
| `default` | 经典蓝 — 沉稳大气，色块小标题 | 科技、商业、通用 |
| `grace` | 优雅紫 — 柔和圆润，左边框小标题 | 文化、美学 |
| `modern` | 暖橙 — 活力大胆，色块小标题 | 自媒体、创业 |
| `simple` | 极简黑 — 极度克制，大量留白 | 思想深度、学术 |

每个主题包含标题（h1-h4）、段落、引用、列表、分割线、图片、代码块、链接、强调色等完整规则。`--list-themes` 列出可用主题；`--color` / `--font-size` 覆盖主色与字号。

---

## 📦 文件结构

```
wechat-article-formatter/
├── SKILL.md                    # Agent 执行指南
├── README.md                   # 本文件
├── QUICKSTART.md               # 快速参考卡
├── EXAMPLES.md                 # 使用示例
├── requirements.txt            # Python 依赖（仅 PyYAML）
│
├── scripts/
│   ├── markdown_to_html.py     # 核心转换器（含 convert_markdown 复用函数）
│   ├── convert-code-blocks.py  # 微信代码块兼容转换
│   ├── batch_convert.py        # 批量转换
│   └── preview_generator.py    # 实时预览（标准库轮询）
│
├── themes/                     # YAML 主题
│   ├── default.yaml
│   ├── grace.yaml
│   ├── modern.yaml
│   └── simple.yaml
│
├── examples/                   # 排版效果示例 HTML
└── references/                 # 参考文档（平台限制、转换详解、主题定制等）
```

---

## 🛠️ 安装依赖

```bash
pip install -r requirements.txt   # 仅 PyYAML；项目根 requirements.txt 已包含
```

核心转换器为纯手写解析器，不依赖 markdown / beautifulsoup4 / cssutils 等外部库；实时预览使用标准库轮询，不依赖 watchdog。

---

## ⚙️ 命令行参数

### markdown_to_html.py

```
-i, --input INPUT       输入的 Markdown 文件路径
-o, --output OUTPUT     输出 HTML 路径（默认同名 .html）
-t, --theme THEME       YAML 主题名（默认：default）
--color COLOR           覆盖主色（如 #A93226）
--font-size SIZE        覆盖字号（如 15px）
--no-preformat          跳过中英文间距与引号预处理
--list-themes           列出可用主题
-p, --preview           转换后在浏览器打开预览
```

### batch_convert.py

```
-i, --input INPUT       Markdown 文件或目录（必需）
-o, --output OUTPUT     输出目录（默认与源文件同目录）
-t, --theme THEME       YAML 主题名（默认：default）
-r, --recursive         递归查找子目录
-w, --workers NUM       并发线程数（默认：4）
-q, --quiet             静默模式，只显示摘要
```

### preview_generator.py

```
-i, --input INPUT       Markdown 文件路径（必需）
-o, --output OUTPUT     输出目录（默认：./preview/）
-t, --theme THEME       YAML 主题名（默认：default）
-p, --port PORT       HTTP 服务器端口（默认：8000）
--no-browser            不自动打开浏览器
```

### convert-code-blocks.py

```
python scripts/convert-code-blocks.py <输入.html> <输出.html>
```

---

## 📖 输出特性

- 所有样式 inline，微信编辑器兼容
- 正文不含文章标题：第一个 H1 在转换时跳过，标题在公众号后台单独填写
- 配图 `![描述](路径)` 保留为 `<img>`；图注自动从 alt 提取（`：` 分隔）
- 同目录存在 `closing.md` 时自动追加到文末
- 预格式化：中英文自动加空格、ASCII 引号转中文引号、多余空行压缩

---

## 🔧 主题自定义（YAML）

```bash
cp themes/default.yaml themes/my-brand.yaml
# 编辑 variables（主色等）与 styles（各元素 CSS），然后：
python scripts/markdown_to_html.py --input article.md --theme my-brand
```

详见 [references/theme-customization.md](references/theme-customization.md)。

---

## ⚠️ 注意事项

- 微信不支持外部 CSS 与 JavaScript：本工具输出全部 inline 样式
- 本地图片无法直接在微信显示：项目发布链路（`openwrite.py publish`）会自动上传正文图片；手工粘贴需在编辑器重新上传
- 代码块必须经 `convert-code-blocks.py` 转换（项目入口自动执行）
- 表格建议 ≤4 列（移动端友好）

详见 [references/wechat-constraints.md](references/wechat-constraints.md)。

---

## 📚 文档导航

- **[SKILL.md](SKILL.md)** - Agent 执行指南
- **[QUICKSTART.md](QUICKSTART.md)** - 快速参考卡
- **[EXAMPLES.md](EXAMPLES.md)** - 使用示例
- **[references/](references/)** - 平台限制、转换详解、发布指南、主题定制

---

## 📄 许可证

MIT（随 OpenWrite 项目）。上游来源见项目根 README。
