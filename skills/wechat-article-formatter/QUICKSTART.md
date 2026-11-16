# 快速参考卡 - WeChat Article Formatter

**3 分钟快速上手指南**

> 项目创作任务请统一使用根命令 `python3 openwrite.py format <文章目录>`（第七步，含状态与可发布性检查）。
> 本卡介绍底层脚本的独立用法，不享受七步状态检查。完整约定见 [SKILL.md](SKILL.md)。

---

## 🚀 最快速的使用方式

### 单行命令（最常用）

```bash
cd /path/to/OpenWrite/skills/wechat-article-formatter
python scripts/markdown_to_html.py --input article.md --theme default --preview
```

**效果**：
- ✅ 转换 Markdown 为 inline-style HTML（微信编辑器兼容）
- ✅ 应用 YAML 主题
- ✅ 自动在浏览器打开预览

---

## 🎨 主题选择（3 秒决策）

| 文章类型 | 主题 | 命令 |
|---------|------|------|
| 科技、商业、通用 | `default`（经典蓝） | `--theme default` |
| 文化、美学 | `grace`（优雅紫） | `--theme grace` |
| 自媒体、创业 | `modern`（暖橙） | `--theme modern` |
| 思想深度、学术 | `simple`（极简黑） | `--theme simple` |

自定义主色/字号：`--color "#A93226"`、`--font-size 15px`；列出主题：`--list-themes`。

---

## 📋 完整工作流（2 分钟）

```bash
# 1. 转换（含中英文间距与引号预处理；保留原文用 --no-preformat）
python scripts/markdown_to_html.py --input "你的文章.md" --theme default --preview

# 2. 含代码块时执行微信兼容转换（项目入口 format 会自动执行）
python scripts/convert-code-blocks.py 你的文章.html 你的文章.html

# 3. 浏览器预览确认后，复制粘贴到微信公众号编辑器
# Ctrl+A → Ctrl+C → 粘贴（不要"粘贴并匹配样式"）→ 发布
```

---

## 🔄 与写作 Skill 配合

**场景**：刚用写作 Skill 完成了文章（项目任务中由 `openwrite.py format` 自动调用本能力）

```bash
# 使用当前任务文章目录的 article.md，不按修改时间猜测文章
python scripts/markdown_to_html.py --input ../../articles/my-topic/article.md --theme default --preview
```

---

## ❌ 常见问题（5 秒解决）

| 问题 | 解决方案 |
|------|---------|
| 代码块不兼容微信 | 运行 `convert-code-blocks.py`（`<pre>` 转为 div+br+nbsp） |
| 粘贴后样式丢失 | 用"粘贴"不要用"粘贴并匹配样式" |
| 图片显示不了 | 项目发布时自动上传正文图片；手工粘贴需在微信编辑器重新上传 |
| 表格太宽 | 减少列数（≤4列）或接受横向滚动 |

---

## 🔧 高级用法

### 批量转换

```bash
python scripts/batch_convert.py --input articles/ --theme grace --workers 8
```

### 实时预览（标准库轮询，无额外依赖）

```bash
python scripts/preview_generator.py --input article.md --theme modern
```

### 自定义主题（YAML）

```bash
# 1. 复制现有主题
cp themes/default.yaml themes/my-brand.yaml

# 2. 编辑 variables 与 styles（见 references/theme-customization.md）

# 3. 使用
python scripts/markdown_to_html.py --input article.md --theme my-brand
```

---

## 📖 需要更多帮助？

- **SKILL.md** - Agent 执行指南（详细步骤）
- **README.md** - 完整功能说明
- **EXAMPLES.md** - 实战示例
- **references/** - 详细技术文档

---

**记住核心**：Markdown → 一键转换 → 复制粘贴 → 发布（2 分钟）
