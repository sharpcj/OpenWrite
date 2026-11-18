---
name: wechat-cover-designer
description: 微信封面排版主题与设计预设。提供数据驱动的封面版式主题（类似格式化主题），定义背景、主体 placement 与文字层次（由主题定义，可达三级）；把任务 cover_style 快照解析为图片能力可消费的有效设计。在 OpenWrite 微信任务第四步生成封面、选择或切换封面版式、定义封面构图与验收规则时使用。不负责取图/渲染（openwrite-images）与封面文案创作（写作 Skill）。
---

# OpenWrite · 微信封面设计

本技能拥有微信封面「长什么样」：版式主题、背景与主体构图、文字层次预设。镜像 [wechat-article-formatter](../wechat-article-formatter/SKILL.md) 的 YAML 主题范式——主题即数据，切换版式无需改代码。

## 职责边界

| 角色 | 负责 |
|---|---|
| **本技能（cover-designer）** | 版式主题、构图/背景/文字层次预设、主题解析 |
| [openwrite-images](../openwrite-images/SKILL.md) | 取图、裁切、Pillow 叠字渲染、导入（执行层） |
| 写作 Skill（如 [wechat-blogger-writer](../wechat-blogger-writer/SKILL.md)） | 封面大标题/副标题/标语文案、主体题材、视觉验收 |

本技能只产出**设计数据**，不另起渲染器；渲染仍由 `openwrite-images/scripts/cover_text.py` 消费主题参数完成。仅作用于微信封面；小红书卡片走 html 渲染，不在此列。

## 主题

主题文件位于 `themes/`，YAML 格式。列出可用主题：

```bash
.venv/bin/python skills/wechat-cover-designer/scripts/cover_themes.py --list
```

当前预设：

| 主题 | 版式别名 | 风格 | 文字层次 |
|---|---|---|---|
| `left-text-right-image` | 左文右图 / left-text-right-image | 平滑暖色渐变 + 右侧紧凑人物剪辑场景 + 左侧文字 | 大标题 + 中副题 + 小标语 |
| `left-text-single-title` | 左文单标题 / left-text-single-title | 同上构图，但左侧仅一个大标题 | 仅大标题 |

**文字层次由主题 `text.levels` 定义**，不是全局默认：主题声明几级就渲染几级，未声明的层次即使写进 `overlay` 也会被裁剪。标题本身够有力的文章可选单标题主题；需要补充信息时选三级主题。

## 主题结构

```yaml
name: 左文右图·暖色人物
description: ...
layout_aliases: [左文右图, left-text-right-image]   # 与 cover_style.layout 匹配
variables: { title-color: "#3D2C22", tagline-color: "#9b8f7f" }
background: { type: gradient, rule: <背景构图约束> }
subject:    { region: right, width_ratio: 0.5, scene: <主体场景>, fit: <紧凑/留白约束> }
text:
  region: left
  width_ratio: 0.45
  position: center-left
  scrim: false
  levels: [title, subtitle, tagline]
  guidance: <左侧文字留白约束>
  title_height_ratio: 0.18
  subtitle_height_ratio: 0.08
  tagline_height_ratio: 0.05
  margin_ratio: 0.06
acceptance: [<可检查的验收项>]
```

## 解析与接入

`cover_themes.design_for(cover_style)` 把任务 `workflow.json.cover_style` 快照（`layout` / `visual_style` / `color_tone`）解析为有效设计：

- `layout` 命中主题（按文件名或 `layout_aliases`）→ 产出构图 instructions + 叠字几何（position / text_width_ratio / scrim）+ style/palette；
- 自定义版式未命中 → 仅把 layout 描述作为构图指引，不强制叠字几何。

`openwrite-images/scripts/produce.py` 的 `_cover_requirement` 调用本解析器，将结果注入有效需求；工作流与图片能力用同一份有效需求校验指纹。账号封面配置（`openwrite.yaml` 的 `wechat.accounts.<号>.cover`）与 `--cover-layout` 等单次覆盖仍按 [封面样式](../../docs/cover-style.md) 规则存入任务快照。

## 封面文字与验收

- 文字层次由主题 `text.levels` 定义，最多三级：大标题（`overlay.title`，可短于文章标题）、中副题（`subtitle`）、小标语（`tagline`，弱化色）。主题声明几级就提供并渲染几级（如单标题主题只有大标题）。
- 底图不渲染文字（`text` 置空），文案由 Pillow 精确叠加。
- 验收按主题 `acceptance` 与写作侧要求实际看图：背景渐变是否平滑、主体是否紧凑靠右留白、文字是否清晰且与边缘留白舒适、是否压主体、有无重影。取得图片并验收后由项目流程提交 `--reviewed --note`。

## 扩展新版式

新增 `themes/<name>.yaml`（含 `layout_aliases`、background/subject/text），即被 `--list` 与解析器自动发现，无需改渲染代码。新增主题应补充对应验收项，并在 [封面样式](../../docs/cover-style.md) 登记。
