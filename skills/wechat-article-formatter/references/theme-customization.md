# 主题自定义指南（YAML 主题系统）

当前排版器使用 **YAML 主题**：每个主题一个文件，放在 `themes/` 目录，包含 `variables`（颜色等变量）与 `styles`（各元素 CSS）。不再使用旧版 CSS 模板文件。

---

## 1. 主题文件结构

```
themes/
├── default.yaml    # 经典蓝
├── grace.yaml      # 优雅紫
├── modern.yaml     # 暖橙
├── simple.yaml     # 极简黑
└── my-brand.yaml   # 你的自定义主题
```

文件名（不含扩展名）即主题名，支持 `.yaml` / `.yml`：

```bash
python scripts/markdown_to_html.py --input article.md --theme my-brand
python scripts/markdown_to_html.py --list-themes
```

---

## 2. 完整示例

```yaml
name: 我的品牌
description: 品牌专用排版

variables:
  primary-color: "#A93226"
  bg-accent-color: "#FFF5F5"

styles:
  h2: "font-size:18px; background:{primary-color}; color:#FFF; padding:6px 14px; border-radius:4px;"
  h3: "font-size:16px; font-weight:bold; color:{primary-color};"
  p: "font-size:15px; line-height:1.8; color:#3a3a3a; margin:10px 0;"
  strong: "color:{primary-color}; font-weight:bold;"
  blockquote: "border-left:3px solid {primary-color}; background:{bg-accent-color}; padding:12px 16px;"
```

- `name` / `description`：展示用标签与说明（`--list-themes` 可见）
- `variables`：自定义变量，供 styles 中 `{变量名}` 引用
- `styles`：各元素的 inline CSS；**可只写需要改的元素**，其余沿用内置默认

---

## 3. 合并与替换规则

样式构建（`_build_styles`）按以下顺序合并：

1. **变量**：内置默认变量 ← 主题 `variables` ← CLI overrides（`--color` 覆盖 `primary-color`，`--font-size` 覆盖 `font-size`）
2. **样式**：内置默认样式 ← 主题 `styles`
3. **变量替换**：所有样式值中的 `{变量名}` 被替换为实际值（支持变量引用变量，最多 3 轮）

### 内置默认变量

| 变量 | 默认值 | 用途 |
|------|--------|------|
| `primary-color` | `#0F4C81` | 主色（标题、强调、链接） |
| `bg-accent-color` | `#F0F4F8` | 强调背景（引用、行内码） |
| `text-color` | `#333333` | 正文颜色 |
| `text-light` / `text-muted` | `#666666` / `#999999` | 次要文字 |
| `bg-light` / `border-color` | `#F7F7F7` / `#EEEEEE` | 浅色背景与边框 |
| `link-color` | `#576B95` | 链接色 |
| `font-size` | `16px` | 全局字号 |
| `font-family` | 系统字体栈 | 全局字体 |
| `line-height` | `1.8` | 全局行高 |
| `paragraph-spacing` | `1.5em` | 段间距 |

### 可定制的元素键

`h1` `h2` `h3` `h4` `p` `strong` `em` `a` `blockquote` `ul` `ol` `li` `hr` `img` `figcaption` `code` `pre` `strong-color`

注意：`h1` 样式存在但第一个 H1 在转换时被移除（公众号标题在后台单独填写）。

---

## 4. 快速上手

### 只换主色（不改文件）

```bash
python scripts/markdown_to_html.py --input article.md --theme default --color "#10b981"
```

### 创建品牌主题

```bash
cp themes/default.yaml themes/my-brand.yaml
# 编辑 variables 的 primary-color / bg-accent-color，按需调整 styles
python scripts/markdown_to_html.py --input article.md --theme my-brand
```

### 从零写一个极简主题

```yaml
name: 极简红
description: 只改主色与强调，其余沿用默认

variables:
  primary-color: "#C0392B"

styles:
  h2: "font-size:17px; font-weight:bold; color:{primary-color}; border-left:4px solid {primary-color}; padding-left:10px;"
  strong: "color:{primary-color}; font-weight:bold;"
```

---

## 5. 微信兼容性注意

- 所有样式必须 inline（主题输出的就是 inline CSS），微信不支持外部 CSS 与 JavaScript
- 避免依赖 `position:fixed`、复杂选择器等微信不支持的特性
- 代码块（`pre`）在发布前由 `convert-code-blocks.py` 转为微信兼容格式，主题中的 `pre` 样式用于本地预览
- 图片样式保留 `max-width:100%` 以适配移动端

平台限制详见 [wechat-constraints.md](wechat-constraints.md)；转换流程详见 [conversion-guide.md](conversion-guide.md)。
