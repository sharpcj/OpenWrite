# 微信封面图样式配置

封面样式由三个独立维度组成。`openwrite.example.yaml` 是模板；在本地 `openwrite.yaml` 的 `wechat.accounts.<账号名>.cover` 下按账号填写：

封面版式由 [wechat-cover-designer](../skills/wechat-cover-designer/SKILL.md) 的**主题预设**驱动，镜像格式化主题的 YAML 范式：每个主题在 `skills/wechat-cover-designer/themes/` 定义背景、主体构图与文字层次（由主题定义，可达三级），`cover_themes.py --list` 可列举。配置用 `cover.theme` 选主题（预设名或别名，如「左文右图」）；`cover.layout` 保留用于自定义构图（不套预设）。已有渲染能力以内的新版式只需加主题文件；新增渲染效果由图片能力实现，再通过主题参数启用。

```yaml
wechat:
  accounts:
    账号1:
      name: ""            # 公众号名，用户填写
      cover:
        theme: left-text-right-image   # 主题预设（或别名「左文右图」）
        visual_style: 温暖插画
        color_tone: 暖黄奶油色
```

| 配置项 | 作用 | 示例 |
|---|---|---|
| `cover.theme` | 选择封面预设主题（名或别名） | left-text-right-image、full-bleed-single-title、tech-glow、左文右图 |
| `cover.layout` | 自定义构图描述（不套预设时改用此项） | 居中标题、上文下图、自定义构图描述 |
| `cover.visual_style` | 图片的视觉表现形式 | 温暖插画、科技线稿、写实摄影、极简抽象、自定义品牌插画 |
| `cover.color_tone` | 全图色彩和氛围 | 暖黄奶油色、青绿渐变、蓝紫渐变、品牌色及色值 |

各项都接受自定义单行描述，不限定为固定套餐。含 `#` 的色值用引号包裹，避免被当作 YAML 注释。每项最长 300 字。`theme` 优先于 `layout` 匹配预设。当前这些配置只作用于微信，且每个账号可以不同；小红书继续使用卡片设计规则。

## 选择和任务快照

各维度分别遵循：**本次用户明确指定 > `openwrite.yaml` 中任务账号的封面配置**。未配置的维度由当次封面设计明确；有歧义时让用户选择，不把主题词当成用户明确指定。

```bash
# 使用账号配置中的默认值
.venv/bin/python openwrite.py new my-topic --title "文章标题"
# 本次改用全幅居中标题主题，其余沿用账号配置
.venv/bin/python openwrite.py new another-topic --title "文章标题" --cover-theme full-bleed-single-title
# 只覆盖视觉风格，主题和色调继续采用各自的配置
.venv/bin/python openwrite.py new third-topic --title "文章标题" --cover-visual-style "科技线稿"
# 自定义构图（不套预设）并指定风格与色调
.venv/bin/python openwrite.py new custom-topic --cover-layout "居中标题" --cover-visual-style "极简抽象" --cover-color-tone "青绿渐变"
```

`new` 和 `workflow init` 将确定的值保存为任务 `workflow.json` 的 `cover_style`，可通过 `workflow status` 查看。配置缺省时不强行给旧流程补默认值；没有该字段的旧任务保持原有需求与图片指纹。

修改 `openwrite.yaml` 只影响新任务。继续已有任务读取其快照；需要修改当前任务时：

```bash
.venv/bin/python openwrite.py workflow cover-style articles/my-topic --cover-color-tone "青绿渐变"
```

该命令只修改明确传入的维度，其他维度沿用当前任务快照，不读取新的全局默认值。封面阶段已经完成时，先 `workflow reset <目录> --from cover` 再修改，并重新生成与验收封面。

## 左文右图·平滑渐变背景

`左文右图` 和 `left-text-right-image` 对应同一种已接入的版式，参考暖色编辑插画风格：

- 整张图使用**奶油白到浅杏橙的平滑连续渐变**，不做硬拼接、独立文字面板或暗色遮罩。账号或任务已指定的风格/色调优先；要严格采用参考配色，应明确选择或清除冲突配置。
- 右侧约 50% 安排**与文章内容对应的完整生活插画场景**，如人物、电脑、木桌、咖啡和绿植。桌面、家具和前景允许自然延伸并裁切至底边，不再要求上下留白，也不固定为剪视频；脸部与关键物件应完整可见。
- 左侧约 45% 保持安静留白。主题自动注入 `effect: warm-editorial`：**品牌/主题大标题 → 较醒目的多行卖点 → 小标语**。英文品牌默认使用英文粗体，中文标题与卖点使用中文粗体，标语使用常规体，可分别用 `font` / `subtitle_font` / `tagline_font` 指定。
- 底图不渲染文字；文案通过 `overlay` 的 `title` / `subtitle` / `tagline` 由 Pillow 精确叠加。`subtitle` 中的 `\n` 明确分行；过长内容还会自动换行和缩字，放不下时报错，不压右侧主体。
- 默认字号为 62 / 44 / 22px，左边距约 48px，整组垂直居中；大标题到卖点间距 52px、卖点到标语 48px，多行间距 10px。可用 `margin_ratio`、`title_subtitle_gap`、`subtitle_tagline_gap`、`line_gap`、`vertical_offset` 及已有字号参数覆盖，三个左侧方位仍可选。
- 默认标题深棕 `#583720`、卖点深棕 `#483326`、标语暖灰 `#928571`，分别由 `color` / `subtitle_color` / `tagline_color` 覆盖。颜色现在是实际渲染默认值，不是未接线的主题变量。该模式只画实心文字，不画光晕、投影、描边、暗层或装饰横线；`scrim` 在该模式不启用。
- 字体、颜色、数值和排版在获取底图前检查。主题默认参数全部进入有效需求指纹。此次修改直接升级原主题名；引用旧主题的已完成任务需 `workflow reset <目录> --from cover`，重新取图/导入并验收，再重做下游；现有图片不会自动覆盖。科技发光和全幅居中主题不受此更改影响。

需求示例中的 `overlay`（大标题可短于文章标题，细节交给副标题/标语）：

```json
{
  "title": "VideoReel",
  "subtitle": "不会剪辑，\n能做宣传视频吗？",
  "tagline": "模板制作 · 先看用途，再看限制"
}
```

没有提供 overlay 时会使用任务标题创建默认叠字需求；但仍应由写作侧给出短大标题、副标题、小标语和合适字色。`text` 必须为空，避免背景生成的文字与程序叠字重复。

## 全幅插画·居中标题

`全幅单标题` / `full-bleed-single-title`（旧别名「left-text-single-title」「左文单标题」仍可解析）**不划分左右区域**：插画按完整封面尺寸铺满整幅画面，唯一的单行大标题在整幅封面水平居中。

- 底图是一整幅暖色编辑插画，构图完整地铺满封面，主体元素偏向画面外圈，中部保留安静的渐变区域承载标题，不再使用左侧独立留白。
- 文字只有一级大标题；`overlay.position` 默认 `center`，也可用 `top-center` / `bottom-center`，排版宽度最多占全图 80%，始终在整幅封面水平居中，长标题换行后仍逐行居中。
- 主题默认关闭遮罩，标题沿用深色 `overlay.color`；标题与背景的对比、是否压住主体细节仍需看图验收。

```json
{
  "title": "剪映困境",
  "color": "#3D2C22"
}
```

其他自定义版式通过构图描述与已有 `overlay.position` / `text_width_ratio` 参数表达，不会被强行转换为左文右图或全幅单标题。是否满足构图要求仍由写作侧视觉验收。

## 深色科技·发光标题

`tech-glow`（别名「科技发光」「深色科技」）移植旧 `cover_text_overlay.py` 的合成方式，而不是让生图模型画文字：

- 深海军蓝底图、右侧与文章有关的科技主体，左侧保持低细节留白；主体题材不固定为机器人或视频剪辑。
- 暗层为 `(6, 12, 38)`、左侧透明度 205，从左向右在全宽 55% 范围内按 smoothstep 平滑归零，不做实心面板。
- 白色大标题 + 冷蓝双层高斯光晕与柔化投影，浅蓝副标题使用较小光晕；标语为弱化浅灰色与轻投影。任何位置都不画装饰横线。
- 默认字号为 92 / 28 / 26px，中文标题优先 Noto Sans CJK Bold，英文副标题优先 DejaVu Sans Bold / Liberation Sans Bold，标语优先中文常规体；其他系统从本机候选字体回退，无可用字体时报错。中文副标题自动选中文字体。可用 `font` / `subtitle_font` / `tagline_font` 明确指定，精确复现需使用相同字体文件。
- 默认左边距 64px，标题到副标题间距 42px、副标题到标语 14px，整组垂直居中上移 6px。文字宽度上限 55%；长文案缩字或换行，不把旧脚本的溢出问题一并复制。实际字形 bbox 偏移会校正，所以不是对旧脚本坐标缺陷的逐像素复刻。
- `text.overlay_defaults` 的全部效果默认值进入有效需求及 `request_hash`。图片能力仍负责生成/导入、真实 PNG 校验与验收，不改工作流门禁。

```bash
# 新任务；明确覆盖已有账号可能配置的暖色维度
.venv/bin/python openwrite.py new tech-topic --cover-theme tech-glow --cover-visual-style "深色科技概念插画" --cover-color-tone "深蓝与冷蓝青色光效"
# 已有任务；已完成封面时先 reset --from cover
.venv/bin/python openwrite.py workflow cover-style articles/my-topic --cover-theme tech-glow --cover-visual-style "深色科技概念插画" --cover-color-tone "深蓝与冷蓝青色光效"
```

只有主题、未配置其他维度时使用科技主题的风格与色调缺省值；账号或任务中已有的 `visual_style` / `color_tone` 仍优先，切主题不会静默删除这些选择。正文排版主题独立，蓝图科技正文仍在第七步选择 `--theme blueprint-tech`。

封面需求只需提供对应文案，主题自动补齐效果参数：

```json
{"title": "连接知识", "subtitle": "OpenWrite · Knowledge", "tagline": "让检索更有依据"}
```

可覆盖 `color` / `subtitle_color` / `tagline_color`、`glow_color` / `subtitle_glow_color`、`glow_radius` / `subtitle_glow_radius`、`panel_color` / `panel_alpha` / `panel_fade_ratio`，以及字号、字体、`margin_ratio`、`title_subtitle_gap` / `subtitle_tagline_gap` / `vertical_offset`。数值和颜色在获取底图前校验，错误参数不触发生图调用。`effect: plain` 可显式关闭科技效果。科技效果只由 `tech-glow` 启用，不会应用到暖色或全幅居中主题。

同一底图、字体和文案可重复生成一致的合成件；重新 AI 生图只能延续风格，不能保证底图像素一致。移植基准来自旧模板，具体历史文章若使用了自定义参数，还须用其脚本/底图逐项对照；不能仅凭模板迁移就声称所有历史封面完全一致。

## 与写作和图片能力的衔接

写作侧按快照组织封面内容、设计和验收规则，配图清单中继续填写主题描述、overlay 标题及关键词句。图片能力统一解析为有效需求：视觉风格进入 `style`，色调进入 `palette`，版式进入 `composition`，左文右图同时约束实际文字排版。

有效需求包含 `cover_style` 快照，执行结果的 `request_hash` 与工作流验收使用同一份有效需求。实际生图后端、来源、字体和文件处理仍由独立图片能力负责，不放回写作 Skill。
