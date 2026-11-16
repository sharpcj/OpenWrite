---
name: rednote-publisher
description: 将已组装的小红书图文产物（3:4 组图 + 笔记文案）发布到创作服务平台。默认仅自己可见，公开需显式授权；支持 dry-run 预演。用于 OpenWrite 小红书任务七步完成且用户明确要求发布时；微信公众号草稿上传使用 wechat-draft-publisher。
---

# OpenWrite · 小红书笔记发布器

## Agent 运行约定

在 OpenWrite 项目中统一通过根目录 `openwrite.py publish <文章目录>` 调用本能力：控制器先校验七步完成、`publish-manifest.json` 指纹与当前产物一致，再按清单顺序（封面首图 + 内容卡片 `order`）传入标题、文案、话题与图片。下方直接脚本命令是底层能力说明，不用于绕过项目阶段检查。

本技能属于 **OpenWrite**，使用宿主提供的命令执行能力与项目已有的 Playwright + Chromium，不引入 Node.js。缺少浏览器依赖时说明缺口（`python3 -m playwright install chromium`），不声称已发布。

## 实现方式与来源

**独立实现的 UI 自动化**：Playwright 打开创作服务平台真实发布页，注入用户 Cookie，上传图片、填写标题正文、选择话题、设置可见范围并点击发布；由站点自身完成请求签名，不复制任何第三方签名代码。

参考的开源项目（仅借鉴协议事实，未复制代码）：

- `comeonzhj/Auto-Redbook-Skills`（MIT）：默认私密 + `--public` 显式公开的产品设计、Cookie 字段要求（`a1` + 登录凭证）。其 vendored 发布运行时提取自 Spider_XHS 且依赖 Node.js，本项目未使用。
- `cv-cat/Spider_XHS`：**无许可证（license: null），保留所有权利**，不得复制其代码、JS 或指纹材料；仅参考其公开描述的接口与页面事实。
- `guizang-social-card-skill` 为 AGPL-3.0，与本项目 MIT 不兼容，未参考其实现。

页面结构可能随平台更新变化；选择器失效时脚本会报告失败步骤并截图，应更新适配器而不是猜测成功。

## 安全与授权闸门

- **默认仅自己可见**。可见范围设置采用失败即中止（fail-closed）：无法确认选中「仅自己可见」时不会点击发布，更不会默认公开。
- **公开必须显式授权**：用户明确要求公开时才传 `--public`；Agent 不得自行决定公开。
- **成功必须实证**：只有观察到站点的成功信号（跳转笔记管理或成功提示）才报告已发布，并尽力提取笔记链接；未确认时报告失败并保留截图，不声称已发布。
- **风险知情**：小红书无官方开放 API，Cookie 会过期且存在风控；平台已公告治理 AI 托管运营账号。首次使用建议先 `--dry-run`，再以默认私密发布实测，确认无误后由用户决定是否公开。发布失败可恢复：修正后重新运行 `publish`，产物未变则无需重新排版。

## 配置

Cookie 与微信凭证共用项目本地 `.env`（`python3 openwrite.py setup` 生成，Git 忽略，权限 600）：

```dotenv
XhsCreatorCookie="a1=...; web_session=...; 其余完整字段"
```

获取方式：浏览器登录 https://creator.xiaohongshu.com → 开发者工具 → 网络 → 复制任一创作平台请求的完整 Cookie（需含 `a1` 与 `web_session` 等登录凭证）。Cookie 失效时脚本会明确提示重新复制。不要把真实 Cookie 写入 `.env.example` 或提交到仓库，也不代用户填写。

## 执行与交付

```bash
# 项目入口（推荐）：七步完成且用户确认后
python3 openwrite.py publish articles/my-note            # 默认仅自己可见
python3 openwrite.py publish articles/my-note --dry-run  # 预演：仅本地校验
python3 openwrite.py publish articles/my-note --public   # 用户明确授权公开
python3 openwrite.py publish articles/my-note --headed   # 有头浏览器，便于观察

# 底层脚本（独立使用时不享受项目阶段检查）
python skills/rednote-publisher/publish_note.py \
  --title "标题" --desc "正文" --images xhs-01-cover.png xhs-02-page.png \
  --topics AI工具 效率 --dry-run
```

- 本地校验：标题 ≤20 字、正文加话题标记 ≤1000 字、图片 1–18 张且存在、话题不带 `#`。
- `--dry-run` 不读取 Cookie、不启动浏览器、不产生任何网络请求。
- 话题在发布页逐个搜索并选择；平台无匹配话题时保留为纯文本并给出警告，不中断发布。
- 失败时在文章目录保存 `publish-failure.png` 截图并报告失败步骤；退出码非零。
- 成功时输出 JSON 结果（`status` / `visibility` / `note_id` / `url`）。笔记链接仅在平台返回时提供。

## 边界

- 只发布已通过第七步组装校验的产物；不修改正文、卡片或清单。
- 不代替用户决定公开可见性，不绕过项目指纹检查，不伪造发布结果。
- 微信公众号任务使用 `wechat-draft-publisher`，两条发布链路互不共用。