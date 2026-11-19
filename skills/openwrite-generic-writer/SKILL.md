---
name: openwrite-generic-writer
description: 约束驱动的通用写作 Skill。用于没有专属写作 Skill 的视角（如新闻记者 news、小说家 novelist）：以任务 brief 的「写作约束（角色预设）」与 workflow.json.writer_profile 快照为最高写作准则，按七步工作流完成正文、封面与配图需求。视角专属 Skill（blogger/tech/product）存在时优先使用专属 Skill，不用本技能。
---

# OpenWrite · 通用写作（角色约束驱动）

本技能不预设写作方法论：**写什么、怎么写、多长、能否虚构，全部由任务的角色约束决定**。约束来自 `writer_roles/<视角>.yaml` 预设，创建任务时已写入 `process/brief.md` 的「写作约束（角色预设）」并快照到 `workflow/workflow.json.writer_profile`。

## 执行顺序

1. 读取任务目录的 `process/brief.md`（主题、受众、用户要求、**写作约束**）与 `workflow status` 输出；约束与用户要求冲突时，先向用户澄清，不擅自取舍。
2. 按 [七步工作流](../../docs/workflow.md) 推进：搜索资料 → 分析资料 → 写正文 → 生成封面 → 生成内容配图 → 生成 Markdown → 生成可发布交付件。阶段门禁以角色快照为准（如 novelist 允许空来源，news 必须搜索）。
3. 配图需求与验收遵循 [配图交接协议](../../docs/image-contract.md)；微信封面版式与叠字规则见 [wechat-cover-designer](../wechat-cover-designer/SKILL.md) 与 [封面样式](../../docs/cover-style.md)。
4. 标题与大纲检查点、发布确认等边界遵循 [AGENT_GUIDE](../../AGENT_GUIDE.md)；本技能不隐含发布授权。

## 约束优先规则

- 角色约束是软约束，由写作 Agent 自觉遵守：长度、图表、时效性、标题风格、虚构许可等按约束文本执行。
- 约束允许虚构时（如 novelist），不得把虚构内容伪装成真实新闻或可核实事实；来源步骤可记录创作参考或说明无需外部来源。
- 约束要求搜索时（如 news），事实、时间、数据必须来自实际检索到的来源，分析用 `source:<id>` 关联。
- 平台表达规格（标题字数、封面尺寸、产物集合）以 `platforms.py` 注册表为准，不因角色约束放宽。

## 平台差异

- 微信：正文写入 `process/draft.md`，封面 `cover.png` 独立上传不嵌正文；第七步由根入口 `format` 排版，主题按任务快照或 `--theme`。
- 小红书：当前仅适配 blogger 视角；本技能被路由到小红书时说明限制并请用户改选视角，不静默切换。