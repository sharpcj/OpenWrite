# 微信公众号草稿发布工具

将 HTML 格式的文章自动推送到微信公众号草稿箱的 通用 Agent 技能（Skill）。

## 功能特性

- ✅ 自动获取和缓存access_token
- ✅ 支持上传封面图片
- ✅ 创建公众号草稿文章
- ✅ 智能错误处理和重试机制
- ✅ 支持命令行和交互式两种模式
- ✅ 完整的日志输出

## 快速开始

### 1. 安装依赖

```bash
pip install requests
```

### 2. 配置微信公众号凭证

在项目根目录生成本地配置（复制 `openwrite.example.yaml` 为 `openwrite.yaml`，已存在则不覆盖）：

```bash
python3 openwrite.py setup
```

编辑项目根目录的 `openwrite.yaml`，在 `wechat.accounts.<账号名>` 下填入 AppID 和 AppSecret（可维护多个公众号账号；每个账号可用可选 `name` 填写公众号名便于识别）：

```yaml
wechat:
  default_account: 账号1
  accounts:
    账号1:
      name: ""            # 公众号名，用户填写
      app_id: wx1234567890abcdef
      app_secret: 你的_appsecret
      author: 你的作者名
```

`openwrite.yaml` 已被 `.gitignore` 忽略，`setup` 会将其权限设为 600。`openwrite.example.yaml` 只是被 Git 跟踪的占位模板，不要写入真实密钥。

**如何获取AppID和AppSecret？**

1. 登录微信公众平台：https://mp.weixin.qq.com
2. 进入"设置与开发" → "基本配置"
3. 在"开发者ID(AppID)"处查看AppID
4. 在"开发者密码(AppSecret)"处重置并获取AppSecret

### 3. 使用项目内 Skill

在 Agent 中打开 OpenWrite 项目，根目录的 `AGENT_GUIDE.md` 会指引读取 `skills/wechat-draft-publisher/SKILL.md`。无需复制到全局技能目录。仅使用本模块时，也可以直接读取本目录的 `SKILL.md`。

## 使用方法

### 方式1：通过 Agent 技能（推荐）

在当前 Agent 中直接说：

```
把这篇文章推送到公众号草稿
标题：Claude Skills：让AI助手秒变领域专家
作者：AI技术观察
封面：./cover.png
内容：article.html
```

或者：

```
推送到公众号：article.html
```

### 方式2：命令行直接调用

**基本用法：**

```bash
python3 publisher.py --title "文章标题" --content article.html
```

**完整参数：**

```bash
python3 publisher.py \
  --title "Claude Skills：让AI助手秒变领域专家" \
  --content article.html \
  --author "AI技术观察" \
  --cover cover.png \
  --digest "本文介绍了Claude Code的Skills系统"
```

**交互式模式：**

```bash
python3 publisher.py --interactive
```

## 参数说明

| 参数 | 简写 | 说明 | 必填 |
|------|------|------|------|
| `--title` | `-t` | 文章标题 | ✅ |
| `--content` | `-c` | HTML内容文件路径 | ✅ |
| `--author` | `-a` | 作者名称 | ❌ |
| `--cover` | - | 封面图片路径 | ❌ |
| `--digest` | `-d` | 文章摘要 | ❌ |
| `--account` | - | 公众号账号名（缺省用唯一账号或 default_account） | ❌ |
| `--interactive` | - | 交互式模式 | ❌ |

## 工作流程

```
┌─────────────────┐
│  读取配置文件   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 获取access_token│ ←── 缓存机制（7200秒有效期）
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  上传封面图片   │ ←── 可选步骤
│  获取media_id   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 组装文章数据    │
│ (标题/内容/封面)│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  调用draft/add  │
│  创建草稿       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  返回结果       │
└─────────────────┘
```

## 常见问题

### Q1: 报错"微信凭证未配置"

**解决方案：**
```bash
# 在项目根目录执行
python3 openwrite.py setup
# 然后编辑 openwrite.yaml，在 wechat.accounts.<账号名> 下填写 app_id 和 app_secret
```

### Q2: 报错"获取access_token失败"

**可能原因：**
- AppID或AppSecret配置错误
- 公众号未认证
- IP白名单未配置

**解决方案：**
1. 检查配置文件中的AppID和AppSecret是否正确
2. 确认公众号已认证（订阅号需要认证才能调用接口）
3. 在公众平台添加服务器IP到白名单

### Q3: 报错"上传图片失败"

**可能原因：**
- 图片格式不支持（支持：jpg/jpeg/png/bmp）
- 图片大小超过限制（封面图需小于2MB）

**解决方案：**
- 转换图片格式或压缩图片大小

### Q4: token缓存在哪里？

缓存文件：`~/.wechat-publisher/token_cache.<appid>.json`（按 AppID 隔离，多账号不串用）

包含：
- `access_token`: token值
- `expires_at`: 过期时间戳
- `updated_at`: 更新时间

## 文件结构

```
wechat-draft-publisher/
├── SKILL.md                          # Skill说明
├── publisher.py                      # Python核心脚本
├── scripts/                          # 安装与辅助脚本
├── examples/example.html             # HTML示例
└── README.md                         # 使用文档

项目根目录/
├── openwrite.example.yaml            # 配置占位模板（被Git跟踪）
└── openwrite.yaml                    # 真实凭证（setup生成，Git忽略）
```

## 技术说明

- **语言**: Python 3.6+
- **依赖**: requests
- **接口**: 微信公众平台 REST API
  - `GET /cgi-bin/token` - 获取access_token
  - `POST /cgi-bin/material/add_material` - 上传图片素材
  - `POST /cgi-bin/draft/add` - 创建草稿

## 安全建议

1. **保护配置文件**
   ```bash
   chmod 600 openwrite.yaml   # openwrite.py setup 已自动设置
   ```

2. **不要提交真实凭证到版本控制**
   - 项目 `.gitignore` 已忽略 `openwrite.yaml`，只跟踪占位模板 `openwrite.example.yaml`
   - 不要把 AppID/AppSecret 写入 `openwrite.example.yaml`、文档或提交信息

3. **定期轮换AppSecret**
   - 在微信公众平台重置AppSecret
   - 更新 `openwrite.yaml` 中对应账号的 `app_secret`

## 更新日志

### v1.0.0 (2025-12-28)
- ✅ 初始版本发布
- ✅ 支持access_token缓存
- ✅ 支持上传封面图片
- ✅ 支持创建草稿文章
- ✅ 交互式和命令行两种模式

## 许可证

MIT License

## 反馈与贡献

如有问题或建议，欢迎提Issue或PR！
