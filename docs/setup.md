# 环境与运行

本文维护安装、运行环境、凭证与本地工具的操作说明。Agent 的正式执行规则从 [AGENT_GUIDE.md](../AGENT_GUIDE.md) 开始；创作阶段与文件协议见 [七步工作流](workflow.md)。

## 环境准备

核心脚本要求 Python 3.8+，依赖为 PyYAML、Requests、Pillow；`requirements.txt` 也包含用于小红书卡片渲染与发布的 Playwright。入口和 Skill 子脚本必须使用同一 Python 环境。

### macOS / Linux 一键初始化

安装好 Python 3 和 Make 后，在项目根目录运行：

```bash
make setup
make doctor
```

`make setup` 创建或复用 `.venv`，优先使用已安装的 uv，否则使用 venv/pip 安装 `requirements.txt`，然后调用 `openwrite.py setup` 生成 `openwrite.yaml`。已有 `openwrite.yaml` 不覆盖，不向系统 Python 安装依赖，不填写密钥、不生图、不发布。依赖安装需要网络，无需手动激活虚拟环境。

缺少工具时，Ubuntu/Debian 可先安装 `make python3 python3-venv`；macOS 的 Make 可通过 Xcode Command Line Tools（`xcode-select --install`）获取。

### 手动初始化

macOS / Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python openwrite.py setup
.venv/bin/python openwrite.py doctor
```

Windows PowerShell：

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe openwrite.py setup
.venv\Scripts\python.exe openwrite.py doctor
```

故事板在 Windows 上双击 `看板.bat` 启动。下文使用 `.venv/bin/python`；Windows 替换为 `.venv\Scripts\python.exe`。其他文档中的 `python3` 同样指已安装项目依赖的解释器。

### 小红书浏览器依赖

```bash
.venv/bin/python -m playwright install chromium
```

一次性下载后，HTML→PNG 卡片渲染可离线运行；发布仍需网络与有效 Cookie。微信任务可以不下载 Chromium。

## 配置与凭证

`openwrite.py setup` 只将 `openwrite.example.yaml` 复制为本地 `openwrite.yaml`，不联网；新文件权限为 600，已被 Git 忽略。已有配置不会覆盖，也不会自动补入模板的新字段，需自行添加。不要把真实凭证写入模板或提交仓库。

配置为嵌套 YAML，按 `defaults → 平台节（wechat/rednote）→ accounts.<账号名> → 任务快照` 四层合并，后者覆盖前者。每个平台可维护多个账号，账号间凭证、视角与封面样式互相隔离。

| 配置内容 | 说明文档 |
|---|---|
| 平台、账号、`defaults.writer_role` 与 `defaults.outline_approval` | [平台与视角选择](task-selection.md) |
| 微信账号封面版式、视觉风格与色调（`cover`） | [封面样式](cover-style.md) |
| ComfyUI、在线生图与图库服务地址/密钥（`image_sources`） | [图片后端配置](../skills/openwrite-images/references/api-configuration.md) |

平台、视角与流程开关只读本地 `openwrite.yaml`（`yaml.safe_load` 解析并校验固定结构），模板不参与运行时解析；图片后端允许进程环境变量（如 `FAL_KEY`）覆盖 `image_sources` 同名字段。`skills/openwrite-images/config.json` 保存模型档案、来源优先级、输出目录与叠字默认值，不放密钥。

### 微信草稿上传

在 `openwrite.yaml` 的 `wechat.accounts.<账号名>` 下填写：

```yaml
wechat:
  default_account: 账号1        # 多账号时的缺省账号；单账号可省略
  accounts:
    账号1:
      name: ""                  # 公众号名，用户填写
      app_id: 你的_appid
      app_secret: 你的_appsecret
      author: 你的作者名        # 可选
```

`name` 可选，由用户填写公众号名，便于识别对应哪个公众号；账号键名（如 `账号1`）才是 `--account` 与任务快照使用的标识符。`author` 可选。未配置必需凭证时，入口在调用微信 API 前报错。发布器不读取旧 `~/.wechat-publisher/config.json`；access_token 按 AppID 分别缓存于 `~/.wechat-publisher/token_cache.<appid>.json`，多账号不串用。上传只是创建草稿，最终群发在微信后台操作。执行前按 [发布协议](workflow.md#发布) 核对产物与授权。

### 小红书发布

在 `openwrite.yaml` 的 `rednote.accounts.<账号名>` 下填写 `cookie`，值为登录 [创作服务平台](https://creator.xiaohongshu.com) 后取得的完整 Cookie，需含 `a1` 与登录凭证。每个账号可用可选 `name` 填写账号名，便于识别对应哪个小红书号。未配置时在启动浏览器前报错；Cookie 过期需更新，发布失败不代表已经发布。

发布默认仅自己可见；公开需用户明确授权并使用 `--public`。`--dry-run` 只做本地校验，不登录、不上传、不发布。命令与成功记录见 [发布协议](workflow.md#发布)，浏览器执行细节见 [发布 Skill](../skills/rednote-publisher/SKILL.md)。

## 命令与路径

```bash
.venv/bin/python openwrite.py --help
.venv/bin/python openwrite.py workflow --help
.venv/bin/python openwrite.py image --help
.venv/bin/python openwrite.py publish --help
```

以上命令在项目根目录运行。入口相对于自身位置查找 Skill；`new` 总在项目 `articles/` 下建任务，其他命令的文章路径相对于调用时工作目录，也支持绝对路径。Skill 文档中的 `scripts/` 相对于该 Skill 目录。项目创作统一使用根入口，底层脚本不提供同样的阶段检查。

详细阶段命令、迁移与返工见 [七步工作流](workflow.md)，图片获取参数见 [图片 Skill](../skills/openwrite-images/SKILL.md)。

## 微信排版选项

主题可选 `default`（经典蓝）、`grace`（优雅紫）、`modern`（暖橙）、`simple`（极简黑）、`blueprint-tech`（蓝图科技）：

```bash
.venv/bin/python openwrite.py format articles/my-topic --theme blueprint-tech
# 保留原始文本，不做预格式化
.venv/bin/python openwrite.py format articles/my-topic --theme blueprint-tech --no-preformat
```

主题也可在 `openwrite.yaml` 的 `wechat.accounts.<账号名>.format_theme` 按账号配置（取值同上或自定义 YAML 主题名）。`new` / `workflow init` 按「显式 `--format-theme` > 账号配置」解析并存入任务快照 `workflow.json.format_theme`；`format` 缺省使用快照主题，`--theme` 显式覆盖并在排版成功后回写快照，重跑不丢失。修改配置只影响新任务；没有快照的旧任务仍用 `default`。小红书卡片主题不受影响。

默认预格式化调整全文中英文间距，以及代码区外成对的 ASCII 双引号；代码区引号保留，但间距处理仍可能影响代码。主题不改变封面或小红书卡片。单纯换主题可直接重跑 `format`；修改上游产物时须按工作流退回。入口自动转换微信代码块，不通过可发布性检查时保留上次成功的 HTML。

批量转换与实时预览脚本已适配 YAML 主题转换器；预览用标准库轮询，无需额外监听依赖。它们属于底层工具，正式任务仍通过根入口排版。

## 实时故事板

```bash
# 方式一：双击项目根目录的 看板.command（macOS）/ 看板.sh（Linux）/ 看板.bat（Windows）
# 方式二：命令行启动（前台运行，Ctrl+C 停止）
.venv/bin/python openwrite.py board
.venv/bin/python openwrite.py board --port 9000 --no-browser
# 停止后台残留的看板进程（非默认端口同时传 --port）
.venv/bin/python openwrite.py board --stop
```

默认地址为 `http://127.0.0.1:8765`，仅绑定本机。看板**不再随 `new` / `workflow init` 自动启动**，需要时双击启动脚本或运行 `board`。双击方式在前台运行：关闭脚本窗口或按 Ctrl+C 即停止服务，浏览器标签页可随手关闭；若已在运行则提示复用现有实例并打开浏览器。Linux 桌面双击 `.sh` 的行为因文件管理器而异：GNOME 需在「文件 → 首选项 → 行为」中选择「运行可执行文本文件」，KDE 可直接运行；也可在终端执行 `./看板.sh`。看板是长驻进程，按代码指纹（核心模块与角色预设的内容哈希）判定新旧：代码更新后再次启动会自动停掉旧进程并以当前代码重启，避免旧代码读不懂新配置/新状态导致看板无数据。

左侧自上而下为：全局统计（已创建微信/小红书任务总数，不受下方过滤影响）、两个账号占比饼图（微信/小红书各账号文章占比，旧文章归入「未指定账号」）、平台与账号选择器（默认微信、账号1，账号名优先显示公众号名 `name`）、日期范围，以及过滤后的任务列表（分页、按创建日期倒序，列表项不再显示平台）。右侧显示选中任务的七步进展和交付件预览。页面每两秒刷新，只读，不修改任务状态、不读取凭证。新任务记录 `created_at`，旧任务回退到状态文件时间。

## 本地检查与排错

`make doctor` 或 `.venv/bin/python openwrite.py doctor` 检查本地依赖、Skill、模板并报告卡片运行时与图片来源配置状态，不联网、不验证 ComfyUI 可达性或凭证有效性。退出码不代表所有可选能力已就绪，仍需查看具体报告。

| 现象 | 处理方式 |
|---|---|
| 找不到依赖或用了系统 Python | 使用项目虚拟环境重新安装 `requirements.txt`，入口与子脚本使用同一解释器 |
| 提示平台需要确认 | 按 [选择规则](task-selection.md) 明确平台，不自动选择首项 |
| 缺少 Chromium | 使用项目解释器执行 `-m playwright install chromium` |
| 原生 Windows 新建任务触发 `fcntl` 错误 | 关闭自动看板后按 `workflow status` 检查已建任务，避免重复创建 |
| 产物指纹过期 | 按错误提示从最早受影响阶段 `workflow reset --from`，详见 [返工与恢复](workflow.md#返工与恢复) |
| 图片尺寸或构图不符 | 核对 `--fit` 的默认行为与需求尺寸，详见 [图片 Skill](../skills/openwrite-images/SKILL.md) |
| 发布凭证缺失或失效 | 在 `openwrite.yaml` 补全或更新对应平台账号凭证，重新检查，未见成功信号不视为发布成功 |
