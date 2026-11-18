# 平台、账号与写作视角选择

平台、账号和视角配置**只来自根目录 `openwrite.yaml`**。`openwrite.example.yaml` 仅是打样模板，供 `.venv/bin/python openwrite.py setup` 复制生成 `openwrite.yaml`，本身不参与任何运行时解析。`openwrite.yaml` 已被 Git 忽略（权限 600），也是各平台凭证的存放位置。文件用 `yaml.safe_load` 解析并校验固定结构，不执行其中任何内容。

```yaml
defaults:
  writer_role: blogger        # blogger / tech / product
  outline_approval: true

wechat:
  default_account: 账号1
  accounts:
    账号1:
      name: ""            # 公众号名，用户填写
      app_id: ""
      app_secret: ""
      author: ""
      # writer_role: tech     # 可选：覆盖该账号的写作视角
      # outline_approval: true
      cover:
        layout: 左文右图
        visual_style: 温暖插画
        color_tone: 暖黄奶油色

rednote:
  default_account: 账号1
  accounts:
    账号1:
      name: ""            # 账号名，用户填写
      cookie: ""
```

平台节为 `wechat` / `rednote`。每个账号可用可选 `name` 填写公众号名/账号名，便于识别；`--account` 与任务快照使用的是账号键名（如 `账号1`、`账号2`），不是 `name`。视角 `defaults.writer_role` 单选：`blogger`（自媒体博主）、`tech`（技术作者）、`product`（产品经理），也接受旧标签 `SelfMediaBlogger` / `TechWriter` / `ProductManager`（大小写不敏感）；缺省或留空默认 `blogger`。微信账号可用 `writer_role` 覆盖全局视角；小红书仅支持 `blogger`，账号不接受该字段。

## 新任务优先级

平台、账号与视角分别处理：

**平台**（账号组）：

1. 当前用户提示词明确指定的选择优先。
2. 未明确指定时，使用唯一启用的平台。平台下账号数 ≥ 1 即视为启用；可加 `enabled: false` 暂停（配置保留）。
3. 没有启用项或同时启用多个平台，且提示词没有明确指定时，必须向用户确认。

**账号**（平台内 `accounts`）：

1. 当前用户提示词明确指定（`--account`）优先。
2. 未指定时，该平台只有一个账号则自动选用；多个账号则用 `default_account`。
3. 多账号且无 `default_account` 时必须向用户确认。只给 `--account` 不给 `--platform` 时，按账号名唯一归属推断平台；同名跨平台则要求同时指定平台。

**写作视角**（`defaults.writer_role`，微信账号可覆盖）：

1. 当前用户提示词明确指定的选择优先。
2. 未明确指定时，微信账号的 `writer_role` 覆盖 > `defaults.writer_role`。
3. 缺省或留空时默认 `blogger`，无需确认；取值非法时报错。

文件不存在时平台没有默认项，视角仍默认博主。未知配置节/字段、非法布尔值、非法 `writer_role`、`default_account` 指向不存在的账号都会报错，不能静默猜测。旧版视角布尔开关与扁平 `.env` 键已废弃。

Agent 负责理解用户提示词的明确意图，转换为命令参数。不会仅凭主题中出现“产品”“技术”“小红书”就猜测平台或视角：例如“分析小红书产品的公众号文章”并不代表发布到小红书。

```bash
# 查看默认解析结果（含账号），不创建任务
.venv/bin/python openwrite.py preferences

# 未传入的项继续按配置解析
.venv/bin/python openwrite.py new rag-guide --title "RAG 入门"

# 用户明确说从产品经理视角写时，仅覆盖当前任务的视角
.venv/bin/python openwrite.py new product-note --title "产品拆解" --perspective product

# 用户明确指定平台与账号，覆盖所有默认值，不修改配置文件
.venv/bin/python openwrite.py new chosen-note --platform wechat --account 账号2 --perspective tech
```

`new` 和 `workflow init` 共用同一选择逻辑。`--type tech/product` 保留为旧版视角参数，与 `--perspective` 不能同时使用。

当平台或账号选择不明确时，命令以非零状态退出，指出需要确认的项，不创建文章目录。Agent 应向用户提出简短明确的问题，收到选择后再传参重试；报错或等待超时都不视为用户已确认。写作视角有内置默认值，不需要询问。

## 任务内持久化

选择确定后写入 `workflow.json` 的 `platform`、`account`、`perspective` 和 `selection_source`。`selection_source` 分别记录选择来自 `explicit`（用户明确选择或用户提示词经 Agent 转换的参数）、`config`（配置值）还是 `default`（视角缺省时的内置默认）。`brief.md` 同时显示平台、账号和视角。

继续同一任务使用这些已保存的选择，不再读取当前默认配置来覆盖任务；`workflow status` 会显示平台、账号和视角。发布时按任务保存的 `account` 取对应凭证，多账号不串用。修改 `openwrite.yaml` 只影响后续新任务，不回写或改变已有任务；修改 `openwrite.example.yaml` 模板不影响任何运行行为。若要制作不同平台、账号或视角的版本，应新建对应任务。

旧版工作流没有这些字段时，沿用微信平台与原有 `type` 视角，不将其偷偷切换为新的默认博主视角，也不自动重写状态文件。

## 视角与能力

微信支持 `blogger` / `tech` / `product`，小红书目前只支持 `blogger`。遇到配置或明确参数产生的不支持组合时，说明限制并取得用户明确选择，不静默覆盖视角或平台。默认博主视角不因主题涉及技术或产品自动切换。写作 Skill 路由统一见 [Agent 指南](../AGENT_GUIDE.md#按阶段读取-skill)。

写作流程检查点也由配置控制：`defaults.outline_approval: true`（默认）要求分析后、写正文前取得用户对三个备选标题与大纲的确认；设为 `false` 表示用户授权跳过；微信账号可用 `outline_approval` 覆盖。该值在 `new` / `workflow init` 时写入任务的 `outline_approval`，与平台、账号、视角一样不随后续配置修改而改变；单次任务也可用 `--skip-outline` 显式授权跳过。

平台适配状态、规格与新增平台接入方式见 [平台适配器契约](platforms.md)；发布操作见 [发布协议](workflow.md#发布)。
