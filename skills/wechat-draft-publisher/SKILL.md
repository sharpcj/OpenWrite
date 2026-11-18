---
name: wechat-draft-publisher
description: 自动将 HTML 文章发布到微信公众号草稿箱，支持封面图上传、标题、作者和元数据管理。当用户说"推送到微信"、"发布到公众号草稿"、"上传到草稿箱"或提到微信文章发布时使用。
---

# OpenWrite · 微信公众号草稿发布器

## Agent 运行约定

在 OpenWrite 项目中统一通过根目录 `openwrite.py` 调用本能力，由项目控制器检查七步完成状态。排版是第七步，使用 `format <文章目录>`；上传使用 `publish <文章目录>`，它要求 `publish-manifest.json` 的指纹与当前产物一致，标题/作者/摘要默认取自该清单（可用 `--title` / `--author` / `--digest` 显式覆盖）。上传账号沿用任务 `workflow.json` 记录的 `account`（创建任务时可用 `new --account` 显式指定），凭证按该账号读取。下方直接脚本命令是底层能力说明，不用于绕过项目阶段检查。

在 OpenWrite 项目中，由根目录 `AGENT_GUIDE.md` 调度本技能。当前文章位于 `articles/<文章目录>/`；所有正文、封面、配图及 HTML 保存到该目录，不写入技能目录。项目任务优先采用用户指定的文章目录；未指定时创建新目录。

本技能属于 **OpenWrite**。使用当前 Agent 的文件读写和命令执行能力，不依赖特定工具名或安装目录。文中的相对路径以本技能目录为基准；输入、输出文件使用明确路径。缺少命令执行能力时提供命令供用户运行，不声称已经转换或上传。发布到微信需要可用网络及用户配置的公众号凭证。

自动将 HTML 格式的文章发布到微信公众号草稿箱，支持封面图上传、标题、作者和摘要等元数据管理。

## ⚡ 快速开始

**最简单的用法：**
```bash
python publisher.py --title "文章标题" --content article.html
```

**完整参数：**
```bash
python publisher.py \
  --title "标题" \
  --content article.html \
  --author "作者名" \
  --cover cover.png \
  --digest "文章摘要"
```

**默认值：**
- 作者：从项目 `openwrite.yaml` 当前账号的 `author` 读取；未配置时首次运行会询问，确认后回写到该账号
- 封面图：`cover.png`

## 📋 执行步骤

**发布文章到微信草稿箱的完整流程：**

1. **查找 HTML 文件**
   - 使用当前任务指定的文章目录中的 `article.html`
   - 若用户提供其他 HTML 路径，使用该明确路径；不按修改时间猜测文章

2. **提取文章标题**
   - 从 HTML 注释提取：`<!-- Title: xxx -->`
   - 从文件名提取
   - 询问用户

3. **检查封面图**
   - 查找 `cover.png`
   - 缺失即中止，不创建无封面的草稿

4. **调用发布脚本**
   ```bash
   python publisher.py --title "xxx" --content xxx.html --cover xxx.png
   ```

5. **验证结果**
   - 创建前保存 in_flight，取得 media_id 后先原子落盘再 draft/get 精确回读
   - 只有 verified 才称为「已上传并核验」；只取得 ID 或退出码 0 不足以证明核验通过

6. **提示用户**
   - 提供微信后台链接
   - 说明下一步操作

## 🔧 配置要求

### 首次使用

1. **获取微信公众号凭证**
   - 访问 https://mp.weixin.qq.com
   - 进入 设置与开发 → 基本配置
   - 复制 AppID 和 AppSecret

2. **生成本地配置并填写**
   ```bash
   # 在项目根目录执行；复制 openwrite.example.yaml 为 openwrite.yaml，已存在则不覆盖
   .venv/bin/python openwrite.py setup
   ```
   编辑项目根目录的 `openwrite.yaml`，在 `wechat.accounts.<账号名>` 下填写 `app_id`、`app_secret`，可选 `author` 与 `name`（公众号名，由用户填写便于识别）。

3. **添加服务器 IP 到白名单**（如需要）

凭证未填写时发布器直接报错并给出上述指引，不再启动交互式密钥输入，也不读取 `~/.wechat-publisher/config.json`。Agent 不代用户填写或猜测凭证。

### 配置文件

**位置：** 项目根目录 `openwrite.yaml`（由 `openwrite.py setup` 从 `openwrite.example.yaml` 复制生成）

**格式：**
```yaml
wechat:
  default_account: 账号1   # 多账号时的缺省账号；单账号可省略
  accounts:
    账号1:
      name: ""            # 公众号名，用户填写
      app_id: wx1234567890abcdef
      app_secret: 你的_appsecret
      author: 你的作者名
```

- `openwrite.yaml` 已被 `.gitignore` 忽略，`setup` 会设置权限 600；`openwrite.example.yaml` 只是被跟踪的占位模板，不要写入真实密钥。
- 运行时只读取 `openwrite.yaml`（`yaml.safe_load` 解析，不执行任何内容），模板不参与解析。
- 可同时维护多个公众号账号；发布按任务账号取凭证，任务创建时可用 `new --account` 显式指定。
- access_token 缓存按 AppID 隔离：`~/.wechat-publisher/token_cache.<appid>.json`，与凭证配置分开。

## ✨ 核心功能

- ✅ access_token 自动缓存（有效期 7200 秒，按 AppID 隔离）
- ✅ 封面图上传和管理
- ✅ HTML 内容自动优化（适配微信）
- ✅ 字段长度自动截断（标题/作者/摘要）
- ✅ 错误处理和重试机制
- ✅ 中文错误提示和解决方案
- ✅ 交互模式和命令行模式

### 可靠性与保守恢复

项目入口使用根目录 `wechat_reliability.py`，在文章 `workflow/wechat-publish.json` 保存所有版本及状态历史。账号 AppID、最终元数据、处理后的 HTML、图片身份和顺序、封面字节共同参与指纹；同指纹已有 ID 时只回读，不重建。每张素材成功立即保存 SHA-256、ID、URL，恢复按账号隔离复用。正文图片失败必须中止；不允许保留本地路径创建草稿。

跨进程文章锁覆盖素材、创建、回读和成功记录。创建 token 在 `in_flight` 前预取，失败确定未发送 add，可在下次显式发布重试；单次 add 消费预取 token，不再次获取。仅明确 token 拒绝白名单 `40001` / `42001` 标为 `rejected`，刷新失败不能掩盖拒绝，下次显式发布可复用素材重试，但同次执行绝不重放 add。`in_flight` 后网络/HTTP 失败、超时、中断、未返回 ID 或非白名单服务错误仍进入 `unknown`，进程硬退出留下的状态下次转为 `unknown`。未知请求即使内容或账号变化也阻止新建。取得 ID 后仅重试读取，最多三次；核对标题、作者、摘要、正文结构/文字与图片顺序和 URL、封面 ID；仅有限规范化 HTML 实体、属性顺序、空元素闭合，以及图片 src/data-src、微信 CDN 白名单内的协议与 /0、/640 尺寸后缀（素材主体和查询参数必须一致）。

恢复必须通过项目入口。`--list-draft-candidates` / `--resume-fingerprint` 提前进入仅查询/旧请求核验分支：沿用任务平台和账号，不要求七步完成、清单有效或当前 HTML/封面存在，不询问作者/标题，也不读取当前正文。只能核验日志保存的旧 article，不上传或创建；候选查询不写成功记录，旧请求也须 verified 才记录。普通新创建及未带旧指纹的 `--bind-media-id` 仍须通过原门禁。底层恢复需显式 `--state-dir`：

```bash
python3 openwrite.py publish articles/<文章目录> --list-draft-candidates
python3 openwrite.py publish articles/<文章目录> \
  --resume-fingerprint <日志中的旧请求指纹> --bind-media-id <人工定位的草稿ID>
```

候选列表仅最近 20 条，未找到不证明未创建；不自动绑定，不解除未知状态，不写成功记录。没有 ID 则保持阻断，交用户在微信后台核对；禁止删除日志、换目录、清除 unknown 或加 force 来自动重建。人工绑定只核验旧请求；错误的未核验候选可重新绑定，创建响应保存的 ID 不可替换。只有 verified 写入带 media_id 与 fingerprint 的 publish-record，保留原平台/标题/可见性/时间字段。详见 [发布协议](../../docs/workflow.md#发布)，含 OS 锁支持、日志丢失/硬故障边界。

本次未验证当前官方 draft/get、batchget 文档正文，契约仅有离线 mock 验证；未做真实微信调用或确认当前官方 HTML 重写行为。不顺带改变字段上限或图片上传 API，token 缓存写逻辑不变。

## 🛠️ 工作流集成

与其他 skill 协同工作：

**完整工作流：**
1. `wechat-tech-writer` → 生成文章（`xxx_article.md` + `cover.png`）
2. `wechat-article-formatter` → 格式化 HTML（`xxx_formatted.html`）
3. `wechat-draft-publisher` → 发布到微信草稿箱（本 skill）

**自动检测机制：**
- 使用当前任务文章目录的 article.html 文件
- 自动查找 `cover.png` 封面图
- 自动识别内容图片

## 🚨 常见问题

### 错误：IP 不在白名单
**症状：** `invalid ip not in whitelist`
**解决：**
1. 登录微信公众号后台
2. 进入 设置 → 基本配置
3. 添加服务器 IP 到白名单

### 错误：AppSecret 错误
**症状：** `AppSecret error`
**解决：**
- 检查项目根目录 `openwrite.yaml` 中对应账号的 `app_id` 和 `app_secret`
- 验证 AppID 以 "wx" 开头（18 个字符）
- 确认 AppSecret 正确

### 错误：标题/作者超出限制
**症状：** `title/author size out of limit`
**解决：**
- 工具会自动截断（标题：32 字节，作者：20 字节）
- 如需调整，修改 `publisher.py`

## 📁 文件结构

```
wechat-draft-publisher/
├── SKILL.md                # 本文件
├── publisher.py            # 核心发布脚本
├── scripts/                # 工具脚本
│   ├── install.sh          # 安装助手（依赖检查 + openwrite.py setup）
│   └── test.sh             # 测试脚本（真实调用微信 API 创建测试草稿）
├── examples/               # 示例文件
│   └── example.html        # HTML 示例
└── README.md               # 详细英文文档
```

## 💡 使用示例

**示例 1：标准发布**
```bash
python publisher.py \
  --title "VSCode 更名事件" \
  --content article.html
```

**示例 2：完整元数据**
```bash
python publisher.py \
  --title "技术文章" \
  --content article.html \
  --author "YanG" \
  --cover images/cover.png \
  --digest "这是一篇关于..."
```

**示例 3：交互模式**
```bash
python publisher.py --interactive
```

## 📱 发布后操作

发布成功后：

1. 登录微信公众号后台
2. 进入"草稿箱"
3. 预览效果
4. 确认后发布

**注意事项：**
- ⚠️ 草稿保存在微信后台，不会立即发布
- ⚠️ 可以在草稿箱中编辑后再发布
- ⚠️ 封面图会在预览时显示

## 🔗 相关文档

- **详细文档：** [README.md](README.md)（英文）
- **安装指南：** [scripts/install.sh](scripts/install.sh)
