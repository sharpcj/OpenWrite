# 微信封面图样式配置

封面样式由三个独立维度组成。`.env.example` 是模板；在本地 `.env` 填写：

```dotenv
WeChatCoverLayout="左文右图"
WeChatCoverVisualStyle="温暖插画"
WeChatCoverColorTone="暖黄奶油色"
```

| 配置项 | 作用 | 示例 |
|---|---|---|
| `WeChatCoverLayout` | 文字与主要画面元素如何摆放 | 左文右图、居中标题、自定义构图描述 |
| `WeChatCoverVisualStyle` | 图片的视觉表现形式 | 温暖插画、科技线稿、写实摄影、极简抽象、自定义品牌插画 |
| `WeChatCoverColorTone` | 全图色彩和氛围 | 暖黄奶油色、青绿渐变、蓝紫渐变、品牌色及色值 |

三项都接受自定义单行描述，不限定为固定套餐。含空格或色值 `#` 时使用引号，避免被当作注释。每项最长 300 字。当前这些配置只作用于微信，小红书继续使用卡片设计规则。

## 选择和任务快照

各维度分别遵循：**本次用户明确指定 > `.env` 中的配置**。未配置的维度由当次封面设计明确；有歧义时让用户选择，不把主题词当成用户明确指定。

```bash
# 使用本地默认值
python3 openwrite.py new my-topic --title "文章标题"
# 只覆盖视觉风格，版式和色调继续采用各自的配置
python3 openwrite.py new another-topic --title "文章标题" --cover-visual-style "科技线稿"
# 三项均按本次需求指定
python3 openwrite.py new custom-topic --cover-layout "左文右图" --cover-visual-style "极简抽象" --cover-color-tone "青绿渐变"
```

`new` 和 `workflow init` 将确定的值保存为任务 `workflow.json` 的 `cover_style`，可通过 `workflow status` 查看。配置缺省时不强行给旧流程补默认值；没有该字段的旧任务保持原有需求与图片指纹。

修改 `.env` 只影响新任务。继续已有任务读取其快照；需要修改当前任务时：

```bash
python3 openwrite.py workflow cover-style articles/my-topic --cover-color-tone "青绿渐变"
```

该命令只修改明确传入的维度，其他维度沿用当前任务快照，不读取新的全局默认值。封面阶段已经完成时，先 `workflow reset <目录> --from cover` 再修改，并重新生成与验收封面。

## 左文右图·一体背景

`左文右图` 和 `left-text-right-image` 对应同一种已接入的版式：

- 整张图使用连续、一致的背景，色调和光照统一，左右自然过渡，不做硬拼接或独立文字面板。
- 主要元素安排在右侧约 45% 区域，左侧约 50% 保持安静和留白。
- 底图不渲染文字；通过已有 `overlay` 排版叠加标题与关键词句。
- 文字默认靠左垂直居中，可使用 `top-left` 或 `bottom-left`；排版宽度最多占全图 45%。长标题自动换行并按可读字号适配，放不下则报错，不把文字扩展到右侧。
- 字色由需求的 `overlay.color` 明确指定，需与背景对比清楚；左文右图默认关闭叠字暗色遮罩，以保留贯通的背景。底图主体是否真的靠右、文字是否压到真实主体，仍需看图验收。

需求示例中的 `overlay`：

```json
{
  "title": "已确认的文章标题",
  "subtitle": "一句关键价值或关键词句",
  "color": "#3D2C22"
}
```

没有提供 overlay 时会使用任务标题创建默认叠字需求；但仍应由写作侧给出关键词句和合适字色。`text` 必须为空，避免背景生成的文字与程序叠字重复。

其他自定义版式通过构图描述与已有 `overlay.position` / `text_width_ratio` 参数表达，不会被强行转换为左文右图。是否满足构图要求仍由写作侧视觉验收。

## 与写作和图片能力的衔接

写作侧按快照组织封面内容、设计和验收规则，配图清单中继续填写主题描述、overlay 标题及关键词句。图片能力统一解析为有效需求：视觉风格进入 `style`，色调进入 `palette`，版式进入 `composition`，左文右图同时约束实际文字排版。

有效需求包含 `cover_style` 快照，执行结果的 `request_hash` 与工作流验收使用同一份有效需求。实际生图后端、来源、字体和文件处理仍由独立图片能力负责，不放回写作 Skill。
