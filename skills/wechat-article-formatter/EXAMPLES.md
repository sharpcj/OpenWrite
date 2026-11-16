# 使用示例 - WeChat Article Formatter

三个典型场景的完整示例。项目创作任务中，第七步由 `python3 openwrite.py format <文章目录>` 自动调用本能力；以下底层脚本用法供独立转换时参考。

---

## 示例 1：单篇技术文章转换（default 经典蓝）

### 场景

刚完成一篇技术文章的 Markdown（项目任务中为 `articles/<名称>/article.md`），需要转换为微信兼容 HTML。

### 步骤

```bash
cd /path/to/OpenWrite/skills/wechat-article-formatter

# 1. 转换（自动进行中英文间距与引号预处理）
python scripts/markdown_to_html.py \
  --input ../../articles/claude-sonnet/article.md \
  --theme default \
  --output ../../articles/claude-sonnet/article.html \
  --preview

# 2. 含代码块时执行微信兼容转换（项目入口 format 会自动执行）
python scripts/convert-code-blocks.py \
  ../../articles/claude-sonnet/article.html \
  ../../articles/claude-sonnet/article.html
```

### 输出特性

- H2 为经典蓝色块小标题，H3 带左边框，层次清晰
- 代码块深色背景；经 `convert-code-blocks.py` 后转为微信支持的 div+br+nbsp 格式
- 引用块左边框 + 浅色背景；图片居中带阴影
- 第一个 H1 被移除（标题在公众号后台单独填写）
- 同目录 `closing.md` 自动追加到文末

### 粘贴到微信

浏览器中 `Ctrl+A` → `Ctrl+C` → 微信编辑器 `Ctrl+V`（用"粘贴"，不要"粘贴并匹配样式"）。项目任务中改用 `openwrite.py publish` 自动上传草稿与图片。

---

## 示例 2：批量转换博客目录（grace 优雅紫）

### 场景

一个目录包含多篇 Markdown，需要统一转换。注意：批量脚本是底层能力，不创建文章工作区、不做七步检查。

```bash
python scripts/batch_convert.py \
  --input /home/user/blog/ \
  --output /home/user/blog/html_output/ \
  --theme grace \
  --recursive \
  --workers 8
```

输出示例：

```
找到 10 个 Markdown 文件；主题: grace；并发数: 8
输出目录: /home/user/blog/html_output/
OK [1/10] AI工具推荐.md → AI工具推荐.html (0.05s)
OK [2/10] Python入门教程.md → Python入门教程.html (0.04s)
...
转换摘要：总数 10，成功 10，失败 0
```

失败的文件会列出原因并以非零码退出；成功的输出不受影响。

---

## 示例 3：边写边预览（modern 暖橙）

### 场景

打磨一篇文章的排版，希望修改 Markdown 后立即看到效果。

```bash
python scripts/preview_generator.py \
  --input article.md \
  --theme modern \
  --port 8080
```

工作流程：
1. 首次转换并在浏览器打开 `http://localhost:8080/article.html`
2. 脚本以标准库轮询监听文件修改时间（无额外依赖）
3. 保存 Markdown 后自动重新转换，刷新浏览器即可
4. `Ctrl+C` 停止服务

不想自动打开浏览器时加 `--no-browser`。

---

## 主题对比与选择

| 主题 | 风格 | 适用 |
|------|------|------|
| `default` | 经典蓝，色块小标题，沉稳大气 | 科技、商业、通用 |
| `grace` | 优雅紫，左边框小标题，柔和圆润 | 文化、美学、读书 |
| `modern` | 暖橙，色块小标题，活力大胆 | 自媒体、创业、生活 |
| `simple` | 极简黑，大量留白，极度克制 | 思想深度、学术 |

```bash
python scripts/markdown_to_html.py --list-themes          # 列出主题
python scripts/markdown_to_html.py --input a.md --theme modern --color "#A93226"  # 覆盖主色
```

---

## 自定义品牌主题（YAML）

```bash
cp themes/default.yaml themes/my-brand.yaml
```

编辑 `my-brand.yaml`：

```yaml
name: 我的品牌
description: 品牌专用排版

variables:
  primary-color: "#A93226"
  bg-accent-color: "#FFF5F5"

styles:
  h2: "font-size:18px; background:{primary-color}; color:#FFF; padding:6px 14px; border-radius:4px;"
  strong: "color:{primary-color}; font-weight:bold;"
  # 其余元素可省略，沿用内置默认规则
```

```bash
python scripts/markdown_to_html.py --input article.md --theme my-brand
```

详见 [references/theme-customization.md](references/theme-customization.md)。

---

## 关键学习点

1. **项目任务走根命令**：`openwrite.py format` 自动完成转换、代码块兼容与可发布性检查
2. **主题即 YAML**：variables + styles，变量替换一键换色
3. **inline 样式**：输出可直接粘贴微信编辑器
4. **代码块必须转换**：微信不支持 `<pre>`，用 `convert-code-blocks.py`
5. **保留原文**：`--no-preformat` 跳过中英文间距与引号预处理
