# 平台与写作视角选择

平台和视角配置**只来自根目录 `.env`**。`.env.example` 仅是打样模板，供 `python3 openwrite.py setup` 复制生成 `.env`，本身不参与任何运行时解析。`.env` 已被 Git 忽略，也是微信凭证的存放位置。文件只按 `KEY=value` 解析，不执行其中的命令，也不做环境变量展开。

```dotenv
WeChat=true
Rednote=false

SelfMediaBlogger=true
TechWriter=false
ProductManager=false
```

平台：`WeChat` → `wechat`，`Rednote` → `rednote`。
视角：`SelfMediaBlogger` → `blogger`（自媒体博主），`TechWriter` → `tech`（技术作者），`ProductManager` → `product`（产品经理）。

## 新任务优先级

平台与视角分别处理：

1. 当前用户提示词明确指定的选择优先。
2. 未明确指定时，使用配置组中唯一为 `true` 的项。
3. 同组没有启用项或同时启用多个项，且提示词没有明确指定时，必须向用户确认。

省略的配置项按关闭处理；文件不存在时，两组都没有默认项。值仅允许 `true` / `false`（大小写不敏感，可以加引号和行尾注释）。重复已知键或非法布尔值会报错，不能静默猜测。

Agent 负责理解用户提示词的明确意图，转换为命令参数。不会仅凭主题中出现“产品”“技术”“小红书”就猜测平台或视角：例如“分析小红书产品的公众号文章”并不代表发布到小红书。

```bash
# 查看默认解析结果，不创建任务
python3 openwrite.py preferences

# 未传入的项继续按配置解析
python3 openwrite.py new rag-guide --title "RAG 入门"

# 用户明确说从产品经理视角写时，仅覆盖当前任务的视角
python3 openwrite.py new product-note --title "产品拆解" --perspective product

# 用户明确指定两个维度，覆盖所有默认值，不修改配置文件
python3 openwrite.py new chosen-note --platform wechat --perspective tech
```

`new` 和 `workflow init` 共用同一选择逻辑。`--type tech/product` 保留为旧版视角参数，与 `--perspective` 不能同时使用。

当选择不明确时，命令以非零状态退出，指出需要确认的平台或视角，不创建文章目录。Agent 应向用户提出简短明确的问题，收到选择后再传参重试；报错或等待超时都不视为用户已确认。已有唯一默认值的另一组不必重复询问。

## 任务内持久化

选择确定后写入 `workflow.json` 的 `platform`、`perspective` 和 `selection_source`。`selection_source` 分别记录选择来自 `config` 还是 `explicit`（用户明确选择或用户提示词经 Agent 转换的参数）。`brief.md` 同时显示平台和视角。

继续同一任务使用这些已保存的选择，不再读取当前默认配置来覆盖任务；`workflow status` 会显示平台和视角。修改 `.env` 只影响后续新任务，不回写或改变已有任务；修改 `.env.example` 模板不影响任何运行行为。若要制作不同平台或视角的版本，应新建对应任务。

旧版工作流没有这两个字段时，沿用微信平台与原有 `type` 视角，不将其偷偷切换为新的默认博主视角，也不自动重写状态文件。

## 视角与能力

微信平台根据任务视角读取相应 Skill：

| 视角 | 写作 Skill |
|---|---|
| `blogger` | `wechat-blogger-writer` |
| `tech` | `wechat-tech-writer` |
| `product` | `wechat-product-manager-writer` |

三种视角共用现有七步流程和独立图片能力。默认博主视角不因主题涉及技术或产品而自动切换。

写作流程检查点也由 `.env` 配置：`OutlineApproval=true`（默认）要求分析后、写正文前取得用户对三个备选标题与大纲的确认；设为 `false` 表示用户授权跳过。该值在 `new` / `workflow init` 时写入任务的 `outline_approval`，与平台、视角一样不随后续配置修改而改变；单次任务也可用 `--skip-outline` 显式授权跳过。

小红书已接入 P0：写作与卡片产物（3:4 组图 + 笔记文案）可正常推进七步；**上传适配器尚未实现**，`publish` 会拒绝并提示手动发布。小红书任务使用 `rednote-note-writer`，不套用微信长文规则。选择解析完成不代表上传能力已接入。

平台产物规格与适配器接线统一登记在根目录 `platforms.py`：微信 `implemented: true`、`publish_implemented: true`；小红书 `implemented: true`、`publish_implemented: false`。写作门禁通过 `platforms.require_pipeline()` 判断，上传另经 `require_publish_adapter()`，不再硬编码单一平台。新增平台的接入清单与分阶段路线见 [平台适配器契约](platforms.md)。
