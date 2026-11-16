---
name: wechat-draft-publisher
description: 自动将 HTML 文章发布到微信公众号草稿箱，支持封面图上传、标题、作者和元数据管理。当用户说"推送到微信"、"发布到公众号草稿"、"上传到草稿箱"或提到微信文章发布时使用。
---

# OpenWrite · 微信公众号草稿发布器

## Agent 运行约定

在 OpenWrite 项目中统一通过根目录 `openwrite.py` 调用本能力，由项目控制器检查七步完成状态。排版是第七步，使用 `format <文章目录>`；上传使用 `publish <文章目录>`，它要求 `publish-manifest.json` 的指纹与当前产物一致，标题/作者/摘要默认取自该清单（可用 `--title` / `--author` / `--digest` 显式覆盖）。下方直接脚本命令是底层能力说明，不用于绕过项目阶段检查。

在 OpenWrite 项目中，由根目录 `AGENTS.md` 调度本技能。当前文章位于 `articles/<文章目录>/`；所有正文、封面、配图及 HTML 保存到该目录，不写入技能目录。项目任务优先采用用户指定的文章目录；未指定时创建新目录。

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
- 作者：从项目 `.env` 的 `WeChatAuthor` 读取；未配置时首次运行会询问，确认后回写到 `.env`
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
   - 如缺失则警告但继续发布

4. **调用发布脚本**
   ```bash
   python publisher.py --title "xxx" --content xxx.html --cover xxx.png
   ```

5. **验证结果**
   - 确认草稿创建成功
   - 获取草稿 media_id

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
   # 在项目根目录执行；复制 .env.example 为 .env，已存在则不覆盖
   python3 openwrite.py setup
   ```
   编辑项目根目录的 `.env`，填写 `WeChatAppID`、`WeChatAppSecret`，可选 `WeChatAuthor`。

3. **添加服务器 IP 到白名单**（如需要）

凭证未填写时发布器直接报错并给出上述指引，不再启动交互式密钥输入，也不读取 `~/.wechat-publisher/config.json`。Agent 不代用户填写或猜测凭证。

### 配置文件

**位置：** 项目根目录 `.env`（由 `openwrite.py setup` 从 `.env.example` 复制生成）

**格式：**
```dotenv
WeChatAppID=wx1234567890abcdef
WeChatAppSecret=你的_appsecret
WeChatAuthor=你的作者名
```

- `.env` 已被 `.gitignore` 忽略，`setup` 会设置权限 600；`.env.example` 只是被跟踪的占位模板，不要写入真实密钥。
- 运行时只读取 `.env`，模板不参与解析；值含空格时用双引号包裹。
- access_token 缓存仍在 `~/.wechat-publisher/token_cache.json`，与凭证配置分开。

## ✨ 核心功能

- ✅ access_token 自动缓存（有效期 7200 秒）
- ✅ 封面图上传和管理
- ✅ HTML 内容自动优化（适配微信）
- ✅ 字段长度自动截断（标题/作者/摘要）
- ✅ 错误处理和重试机制
- ✅ 中文错误提示和解决方案
- ✅ 交互模式和命令行模式

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
- 检查项目根目录 `.env` 中的 `WeChatAppID` 和 `WeChatAppSecret`
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
