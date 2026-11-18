#!/usr/bin/env python3
"""Publish a Rednote image note through the creator platform's publish page.

Independent implementation: Playwright drives the real publish page so the
site signs its own requests — no third-party signing code, no Node.js. Only
protocol facts (publish page URL, visibility semantics, cookie fields) were
referenced from open-source projects; see SKILL.md for sources and licenses.

Safety properties:
- Visibility is fail-closed: publishing aborts unless the intended privacy
  option is confirmed selected; the default is private (仅自己可见).
- Success is never claimed without an observed success signal from the site.
- Failures leave a screenshot for diagnosis and exit non-zero.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CREATOR_ORIGIN = 'https://creator.xiaohongshu.com'
PUBLISH_URL_PATH = '/publish/publish?source=official&from=menu&target=image'
# Keep in sync with platforms.REGISTRY['rednote']['limits'].
TITLE_CHARS = 20
DESC_CHARS = 1000
MAX_IMAGES = 18
# A usable creator cookie carries a1 plus at least one login session field.
SESSION_KEYS = ('web_session', 'customer-sso-sid',
                'access-token-creator.xiaohongshu.com', 'galaxy_creator_session_id')
SUCCESS_TEXTS = ('发布成功', '已发布', '发布完成')


def load_preferences(root: Path):
    """Load the project config module so credentials follow the same rules."""
    path = root / 'preferences.py'
    if not path.is_file():
        raise FileNotFoundError(f'找不到项目配置模块: {path}')
    spec = importlib.util.spec_from_file_location('openwrite_preferences', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_cookie(text: str) -> dict:
    values = {}
    for item in text.split(';'):
        if '=' not in item:
            continue
        key, value = item.strip().split('=', 1)
        if key:
            values[key] = value
    return values


def validate_cookie(text: str) -> dict:
    cookies = parse_cookie(text)
    if not cookies.get('a1'):
        raise ValueError('Cookie 缺少 a1 字段；请复制创作服务平台请求中的完整 Cookie')
    if not any(cookies.get(key) for key in SESSION_KEYS):
        raise ValueError('Cookie 缺少登录凭证（web_session 等）；请复制已登录创作服务平台的完整 Cookie')
    return cookies


def validate_note(title: str, desc: str, images: list, topics: list) -> list:
    """Local checks shared by dry-run and real publishing; no network needed."""
    if not title or not title.strip():
        raise ValueError('标题不能为空')
    if len(title) > TITLE_CHARS:
        raise ValueError(f'标题不能超过 {TITLE_CHARS} 字（当前 {len(title)}）')
    if not desc or not desc.strip():
        raise ValueError('笔记正文不能为空')
    for topic in topics:
        if not topic.strip() or '#' in topic:
            raise ValueError(f'话题名称非法：{topic}（非空且不带 #）')
    # 话题在平台上以 #名称[话题]# 计入正文长度。
    marked = desc + ''.join(f' #{topic}[话题]# ' for topic in topics)
    if len(marked) > DESC_CHARS:
        raise ValueError(f'正文加话题标记超过 {DESC_CHARS} 字（当前 {len(marked)}）')
    paths = []
    for raw in images:
        path = Path(raw).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f'图片不存在：{raw}')
        paths.append(path)
    if not 1 <= len(paths) <= MAX_IMAGES:
        raise ValueError(f'图片数量必须为 1–{MAX_IMAGES} 张（当前 {len(paths)}）')
    return paths


class RednotePublisher:
    """Drive the creator publish page with Playwright; verify before claiming."""

    def __init__(self, root=None, base_url: str = CREATOR_ORIGIN, headed: bool = False,
                 timeout: float = 120, artifact_dir=None, publish_url: str = None, account=None):
        self.root = Path(root).expanduser().resolve() if root else PROJECT_ROOT
        self.base_url = base_url.rstrip('/')
        self.publish_url = publish_url or self.base_url + PUBLISH_URL_PATH
        self.headed = headed
        self.timeout_ms = int(timeout * 1000)
        self.artifact_dir = Path(artifact_dir).expanduser().resolve() if artifact_dir else None
        self.account = account
        self.preferences = load_preferences(self.root)

    def publish(self, title: str, desc: str, images: list, topics: list, public: bool = False) -> dict:
        paths = validate_note(title, desc, images, topics)
        cookie_text = self.preferences.require_xhs_cookie(self.root, self.account)
        cookies = validate_cookie(cookie_text)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not self.headed)
            try:
                context = browser.new_context(viewport={'width': 1440, 'height': 900}, locale='zh-CN')
                context.add_cookies(self._browser_cookies(cookies))
                page = context.new_page()
                page.set_default_timeout(self.timeout_ms)
                return self._run_flow(page, title, desc, paths, topics, public)
            finally:
                browser.close()

    def _browser_cookies(self, cookies: dict) -> list:
        host = urlparse(self.base_url).hostname or 'creator.xiaohongshu.com'
        if host in ('localhost', '127.0.0.1') or host.replace('.', '').isdigit():
            domain = host
        else:
            domain = '.' + '.'.join(host.split('.')[-2:])
        return [{'name': key, 'value': value, 'domain': domain, 'path': '/'}
                for key, value in cookies.items()]

    def _run_flow(self, page, title, desc, paths, topics, public):
        step = '打开发布页'
        try:
            page.goto(self.publish_url, wait_until='domcontentloaded')
            self._require_logged_in(page)
            step = '上传图片'
            self._upload(page, paths)
            step = '填写标题'
            self._title_input(page).fill(title)
            step = '填写正文'
            self._editor(page).fill(desc)
            step = '添加话题'
            self._add_topics(page, topics)
            step = '设置可见范围'
            self._set_visibility(page, public)
            step = '点击发布'
            self._click_publish(page)
            step = '确认发布结果'
            return self._confirm_success(page, public)
        except Exception as exc:
            shot = self._screenshot(page)
            where = f'（失败步骤：{step}；截图：{shot}）' if shot else f'（失败步骤：{step}）'
            raise ValueError(f'小红书发布失败{where}：{exc}') from exc

    def _require_logged_in(self, page):
        url = page.url.lower()
        if 'login' in url or 'passport' in url:
            raise ValueError('Cookie 已失效或未被识别（跳转到登录页）；'
                             '请重新登录创作服务平台并更新 openwrite.yaml 中对应账号的 cookie')
        for text in ('扫码登录', '手机号登录'):
            locator = page.get_by_text(text).first
            if locator.count() and locator.is_visible():
                raise ValueError('页面要求登录，Cookie 已失效；请重新登录创作服务平台并更新 openwrite.yaml 中对应账号的 cookie')

    def _upload(self, page, paths):
        upload = page.locator('input[type="file"]').first
        upload.wait_for(state='attached')
        upload.set_input_files([str(path) for path in paths])
        # 编辑区出现即表示上传完成。
        self._title_input(page).wait_for(state='visible')

    def _title_input(self, page):
        for selector in ('input[placeholder*="标题"]', 'input[maxlength="20"]', '#title'):
            locator = page.locator(selector).first
            if locator.count():
                return locator
        raise ValueError('找不到标题输入框；页面结构可能已变化，请用 --headed 观察并反馈更新适配器')

    def _editor(self, page):
        for selector in ('.ql-editor', 'div[contenteditable="true"]', '#desc'):
            locator = page.locator(selector).first
            if locator.count():
                return locator
        raise ValueError('找不到正文编辑器；页面结构可能已变化，请用 --headed 观察并反馈更新适配器')

    def _add_topics(self, page, topics):
        if not topics:
            return
        editor = self._editor(page)
        for topic in topics:
            editor.click()
            page.keyboard.press('Control+End')
            page.keyboard.type(f'#{topic}')
            page.wait_for_timeout(600)
            picked = False
            for selector in (f'.topic-item:has-text("{topic}")',
                             f'[class*="topic"] li:has-text("{topic}")',
                             f'#topic-suggest button:has-text("{topic}")',
                             f'li:has-text("{topic}")'):
                item = page.locator(selector).first
                if item.count() and item.is_visible():
                    item.click()
                    picked = True
                    break
            if not picked:
                print(f'警告：话题「{topic}」未找到匹配项，保留为纯文本', file=sys.stderr)

    def _set_visibility(self, page, public):
        label = '公开' if public else '仅自己可见'
        more = page.get_by_text('更多设置', exact=False).first
        if more.count() and more.is_visible():
            more.click()
            page.wait_for_timeout(300)
        target = None
        for locator in (page.get_by_text(label, exact=True).first,
                        page.locator(f'label:has-text("{label}")').first):
            if locator.count() and locator.is_visible():
                target = locator
                break
        if target is None:
            raise ValueError(f'找不到可见范围选项「{label}」；为安全起见中止发布，不会默认公开')
        target.click()
        page.wait_for_timeout(300)
        if not self._visibility_confirmed(page, public):
            raise ValueError(f'无法确认可见范围已设为「{label}」；为安全起见中止发布')

    def _visibility_confirmed(self, page, public) -> bool:
        value = 'public' if public else 'private'
        radio = page.locator(f'input[type="radio"][value="{value}"]').first
        if radio.count():
            return radio.is_checked()
        label = '公开' if public else '仅自己可见'
        selected = page.locator(f'[aria-checked="true"]:has-text("{label}"), '
                                f'[class*="active"]:has-text("{label}"), '
                                f'[class*="checked"]:has-text("{label}"), '
                                f'[class*="selected"]:has-text("{label}")').first
        return bool(selected.count())

    def _click_publish(self, page):
        for locator in (page.get_by_role('button', name='发布', exact=True).first,
                        page.locator('button:has-text("发布"):not(:has-text("定时"))').first,
                        page.locator('.publishBtn, button.publish, #publish').first):
            if locator.count() and locator.is_visible():
                locator.click()
                return
        raise ValueError('找不到发布按钮；页面结构可能已变化，请用 --headed 观察并反馈更新适配器')

    def _confirm_success(self, page, public) -> dict:
        deadline = time.monotonic() + self.timeout_ms / 1000
        confirmed = False
        while time.monotonic() < deadline:
            url = page.url
            if 'note-manager' in url or 'publish/success' in url:
                confirmed = True
                break
            if any(page.get_by_text(text).first.is_visible()
                   for text in SUCCESS_TEXTS if page.get_by_text(text).count()):
                confirmed = True
                break
            page.wait_for_timeout(500)
        if not confirmed:
            raise ValueError('未观察到发布成功信号，不声称已发布；'
                             '请用 --headed 复查，或到创作服务平台笔记管理确认后再决定重试')
        note_id = self._find_note_id(page)
        return {'status': 'published', 'visibility': 'public' if public else 'private',
                'note_id': note_id,
                'url': f'https://www.xiaohongshu.com/explore/{note_id}' if note_id else None}

    def _find_note_id(self, page):
        parsed = urlparse(page.url)
        for source in (parsed.query, parsed.fragment):
            query = parse_qs(source.split('?', 1)[-1])
            for key in ('note_id', 'noteId', 'id'):
                if query.get(key):
                    return query[key][0]
        link = page.locator('a[href*="/explore/"]').first
        if link.count():
            href = link.get_attribute('href') or ''
            return href.rstrip('/').split('/')[-1] or None
        return None

    def _screenshot(self, page):
        try:
            directory = self.artifact_dir or Path.cwd()
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / 'publish-failure.png'
            page.screenshot(path=str(path), full_page=True)
            return path
        except Exception:
            return None


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='通过创作服务平台发布页发布小红书图文笔记（默认仅自己可见）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  # 发布预演：仅本地校验，不登录、不上传、不发布
  python publish_note.py --title "标题" --desc "正文" --images xhs-01-cover.png xhs-02-page.png --dry-run

  # 默认仅自己可见
  python publish_note.py --title "标题" --desc "正文" --images xhs-01-cover.png xhs-02-page.png

  # 公开发布需显式授权
  python publish_note.py --title "标题" --desc "正文" --images *.png --public --topics AI工具 效率
''')
    parser.add_argument('--title', required=True, help=f'笔记标题（不超过 {TITLE_CHARS} 字）')
    parser.add_argument('--desc', required=True, help='笔记正文文案')
    parser.add_argument('--images', nargs='+', required=True, help='按上传顺序排列的图片路径，封面为首图')
    parser.add_argument('--topics', nargs='*', default=[], help='话题名称，不带 #')
    parser.add_argument('--public', action='store_true', help='公开发布；默认仅自己可见')
    parser.add_argument('--dry-run', action='store_true', help='仅本地参数校验，不登录、不上传、不发布')
    parser.add_argument('--headed', action='store_true', help='使用有头浏览器，便于观察过程或协助登录')
    parser.add_argument('--timeout', type=float, default=120, help='单步与结果确认超时（秒）')
    parser.add_argument('--project-root', help='项目根目录（读取 openwrite.yaml），默认为脚本所在项目')
    parser.add_argument('--account', help='小红书账号名（openwrite.yaml 中 rednote.accounts 下的键；缺省用唯一账号或 default_account）')
    parser.add_argument('--base-url', default=CREATOR_ORIGIN, help='创作服务平台地址（测试可指向本地模拟页）')
    parser.add_argument('--artifact-dir', help='失败截图保存目录，通常为文章目录')
    return parser


def main(argv=None) -> int:
    args = create_parser().parse_args(argv)
    try:
        paths = validate_note(args.title, args.desc, args.images, args.topics)
        visibility = '公开' if args.public else '仅自己可见'
        if args.dry_run:
            print('发布预演：参数校验通过，不会登录、上传或发布')
            print(f'标题：{args.title}')
            print(f'正文：{len(args.desc)} 字；话题：{"、".join(args.topics) or "无"}')
            print(f'图片：{len(paths)} 张（封面为首图）')
            print(f'可见性：{visibility}')
            return 0
        publisher = RednotePublisher(root=args.project_root, base_url=args.base_url,
                                     headed=args.headed, timeout=args.timeout,
                                     artifact_dir=args.artifact_dir, account=args.account)
        result = publisher.publish(args.title, args.desc, args.images, args.topics, public=args.public)
        print('小红书笔记发布成功')
        print(json.dumps(result, ensure_ascii=False))
        if result.get('url'):
            print(f'笔记链接：{result["url"]}')
        print(f'可见性：{visibility}')
        return 0
    except KeyboardInterrupt:
        print('操作已取消', file=sys.stderr)
        return 130
    except Exception as exc:
        print(f'错误：{exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
