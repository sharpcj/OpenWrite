# 微信封面图样式配置

封面样式由三个独立维度组成。`openwrite.example.yaml` 是模板；在本地 `openwrite.yaml` 的 `wechat.accounts.<账号名>.cover` 下按账号填写：

封面版式由 [wechat-cover-designer](../skills/wechat-cover-designer/SKILL.md) 的**主题预设**驱动，镜像格式化主题的 YAML 范式：每个主题在 `skills/wechat-cover-designer/themes/` 定义背景、主体构图与文字层次（由主题定义，可达三级），`cover_themes.py --list` 可列举。配置用 `cover.theme` 选主题（预设名或别名，如「左文右图」）；`cover.layout` 保留用于自定义构图（不套预设）。新增版式只需加主题文件，无需改渲染代码。

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
| `cover.theme` | 选择封面预设主题（名或别名） | left-text-right-image、full-bleed-single-title、左文右图 |
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

- 整张图使用**平滑连续的暖色渐变背景**，色调从左到右柔和过渡，不做硬拼接、独立文字面板或生硬的颜色切断。
- 右侧约 50% 安排**一个完整的暖色编辑插画场景**（优先是一个友好的人物坐在桌前用电脑剪视频，周围漂浮少量视频片段/播放键/UI 卡片），场景有呼吸空间，不填满边缘。
- 左侧约 45% 保持安静留白承载文字。**文字层次由主题定义**：该主题为三级（大标题粗体深色最大、中副题中等字号、小标语弱化灰色小字），按主题 `text.levels` 提供文案。
- 底图不渲染文字；文案通过 `overlay` 的 `title` / `subtitle` / `tagline` 由 Pillow 精确叠加，实际渲染层次以主题 `text.levels` 为准。
- 文字默认靠左垂直居中，可使用 `top-left` 或 `bottom-left`（主题只接受左侧方位）；排版宽度最多占全图 45%。长文案自动换行并按可读字号适配，放不下则报错，不把文字扩展到右侧。
- 大标题字色由 `overlay.color` 指定（需与背景对比清楚），小标语字色由 `overlay.tagline_color` 指定（默认弱化暖灰 `#9b8f7f`）；该主题默认关闭叠字暗色遮罩与偏移阴影，保留贯通背景、避免重影。底图主体是否靠右、文字是否压到主体，仍需看图验收。

需求示例中的 `overlay`（大标题可短于文章标题，细节交给副标题/标语）：

```json
{
  "title": "AI 杀不死剪映",
  "subtitle": "一年赚走近百亿",
  "tagline": "真正危险的是别人",
  "color": "#3D2C22"
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

## 与写作和图片能力的衔接

写作侧按快照组织封面内容、设计和验收规则，配图清单中继续填写主题描述、overlay 标题及关键词句。图片能力统一解析为有效需求：视觉风格进入 `style`，色调进入 `palette`，版式进入 `composition`，左文右图同时约束实际文字排版。

有效需求包含 `cover_style` 快照，执行结果的 `request_hash` 与工作流验收使用同一份有效需求。实际生图后端、来源、字体和文件处理仍由独立图片能力负责，不放回写作 Skill。
