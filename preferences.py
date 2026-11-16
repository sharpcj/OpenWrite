"""Project-local defaults; explicit task choices win and are persisted by the caller.

Runtime configuration is read only from the local `.env` (Git-ignored).
`.env.example` is a tracked sample used solely by `init_env` to create `.env`;
it never participates in resolution. Values are parsed as plain text; nothing
in the file is executed or expanded.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shlex
import tempfile

PLATFORMS = {'WeChat': 'wechat', 'Rednote': 'rednote'}
PERSPECTIVES = {'SelfMediaBlogger': 'blogger', 'TechWriter': 'tech', 'ProductManager': 'product'}
PLATFORM_LABELS = {'wechat': '微信', 'rednote': '小红书'}
PERSPECTIVE_LABELS = {'blogger': '自媒体博主', 'tech': '技术作者', 'product': '产品经理'}

TEMPLATE_NAME = '.env.example'
ENV_NAME = '.env'
# Boolean workflow features; the value is the default when the key is absent.
FEATURES = {'OutlineApproval': True}
# WeChat publishing credentials; real values belong in .env, never in the template.
CREDENTIALS = {'WeChatAppID': 'appid', 'WeChatAppSecret': 'appsecret', 'WeChatAuthor': 'author'}
# Rednote creator-platform cookie; real values belong in .env, never in the template.
XHS_CREDENTIALS = {'XhsCreatorCookie': 'cookie'}
# Single-valued writer role; the legacy boolean perspective switches are rejected.
WRITER_ROLE_KEY = 'WriterRole'
DEFAULT_WRITER_ROLE = 'SelfMediaBlogger'
KNOWN_KEYS = set(PLATFORMS) | {WRITER_ROLE_KEY} | set(CREDENTIALS) | set(XHS_CREDENTIALS)
PLACEHOLDERS = {'', 'your_appid', 'your_appid_here', 'your_appsecret', 'your_appsecret_here',
                'your_author', 'your_author_here', 'changeme',
                'your_cookie', 'your_cookie_here', 'your_xhs_cookie_here'}


class ChoiceRequired(ValueError):
    """The agent must obtain an explicit user choice instead of guessing."""


def parse_env(path: Path) -> dict:
    """Read KEY=value lines as strings; quotes and trailing comments are honoured."""
    values = {}
    for number, raw in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].lstrip()
        key, separator, value = line.partition('=')
        key = key.strip()
        if not separator:
            raise ValueError(f'{path.name} 第 {number} 行需要 KEY=value 格式')
        if key in values:
            raise ValueError(f'{path.name} 中 {key} 重复配置')
        lexer = shlex.shlex(value, posix=True)
        lexer.whitespace_split = True
        lexer.commenters = '#'
        try:
            tokens = list(lexer)
        except ValueError as exc:
            raise ValueError(f'{path.name} 第 {number} 行的 {key} 引号不完整：{exc}')
        values[key] = ' '.join(tokens)
    return values


def read_values(root: Path) -> dict:
    """Read the local .env only; the tracked template is never used at runtime."""
    path = root / ENV_NAME
    return parse_env(path) if path.is_file() else {}


def read_config(root: Path) -> dict:
    """Boolean platform flags; the writer role is single-valued via WriterRole."""
    flags = {}
    for key, value in read_values(root).items():
        if key not in PLATFORMS:
            continue
        if value.lower() not in ('true', 'false'):
            raise ValueError(f'{ENV_NAME} 中的 {key} 只能为 true 或 false')
        flags[key] = value.lower() == 'true'
    return flags


def writer_role(root: Path) -> tuple:
    """Resolve WriterRole into (perspective, selection_source).

    Absent or empty falls back to the blogger default. Legacy boolean
    perspective switches are rejected instead of silently ignored.
    """
    values = read_values(root)
    legacy = [key for key in PERSPECTIVES if key in values]
    if legacy:
        raise ValueError(f'{ENV_NAME} 中的旧版视角开关 {"、".join(legacy)} 已废弃；'
                         f'请改用 {WRITER_ROLE_KEY}（{" / ".join(PERSPECTIVES)}，默认 {DEFAULT_WRITER_ROLE}）')
    raw = values.get(WRITER_ROLE_KEY, '').strip()
    if not raw:
        return PERSPECTIVES[DEFAULT_WRITER_ROLE], 'default'
    for label, perspective in PERSPECTIVES.items():
        if raw.casefold() == label.casefold():
            return perspective, 'config'
    raise ValueError(f'{ENV_NAME} 中的 {WRITER_ROLE_KEY} 只能为 {" / ".join(PERSPECTIVES)}（当前：{raw}）')


def feature_flags(root: Path) -> dict:
    """Read boolean workflow features from .env; absent keys use their default."""
    values = read_values(root)
    flags = {}
    for key, default in FEATURES.items():
        raw = values.get(key)
        if raw is None or not raw.strip():
            flags[key] = default
            continue
        if raw.strip().lower() not in ('true', 'false'):
            raise ValueError(f'{ENV_NAME} 中的 {key} 只能为 true 或 false')
        flags[key] = raw.strip().lower() == 'true'
    return flags


def outline_approval(root: Path) -> bool:
    """Whether the title/outline checkpoint requires explicit user approval."""
    return feature_flags(root)['OutlineApproval']


def resolve(root: Path, platform=None, perspective=None) -> dict:
    for label, supplied, choices in [('平台', platform, PLATFORM_LABELS),
                                     ('写作视角', perspective, PERSPECTIVE_LABELS)]:
        if supplied is not None and supplied not in choices:
            raise ValueError(f'未知{label}：{supplied}')
    flags = read_config(root)
    result, selection_source, missing = {}, {}, []
    if platform is not None:
        result['platform'] = platform
        selection_source['platform'] = 'explicit'
    else:
        enabled = [value for key, value in PLATFORMS.items() if flags.get(key, False)]
        if len(enabled) == 1:
            result['platform'] = enabled[0]
            selection_source['platform'] = 'config'
        else:
            reason = '没有唯一启用项' if not enabled else '同时启用了多个选项'
            missing.append(f'平台{reason}，请向用户明确确认后传入 --platform ({" / ".join(PLATFORMS.values())})')
    if perspective is not None:
        result['perspective'] = perspective
        selection_source['perspective'] = 'explicit'
    else:
        result['perspective'], selection_source['perspective'] = writer_role(root)
    if missing:
        raise ChoiceRequired('；'.join(missing))
    result['selection_source'] = selection_source
    return result


def task_platform(state: dict) -> str:
    # Legacy tasks were WeChat-only; never re-read current defaults for existing work.
    return state.get('platform', 'wechat')


def task_perspective(state: dict) -> str:
    return state.get('perspective', state.get('type', 'tech'))


def init_env(root: Path) -> tuple:
    """Copy the template to a local .env once; never overwrite existing values."""
    template, target = root / TEMPLATE_NAME, root / ENV_NAME
    if os.path.lexists(target):
        if target.is_symlink():
            raise ValueError(f'{ENV_NAME} 不能是符号链接')
        return target, False
    if not template.is_file():
        raise ValueError(f'缺少配置模板：{template}')
    target.write_text(template.read_text(encoding='utf-8'), encoding='utf-8')
    target.chmod(0o600)
    return target, True


def _format_value(value: str) -> str:
    if not value:
        return ''
    if re.fullmatch(r'[^\s#"\'\\]+', value):
        return value
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def set_env_value(root: Path, key: str, value: str) -> Path:
    """Update one known key in the local .env, keeping other lines and comments."""
    if key not in KNOWN_KEYS:
        raise ValueError(f'未知配置项：{key}')
    target = root / ENV_NAME
    if not target.is_file():
        raise ValueError(f'缺少本地配置 {target}；请先运行 python3 openwrite.py setup')
    lines = target.read_text(encoding='utf-8').splitlines()
    replacement = f'{key}={_format_value(value)}'
    for index, raw in enumerate(lines):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].lstrip()
        if line.partition('=')[0].strip() == key:
            lines[index] = replacement
            break
    else:
        lines.append(replacement)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=root,
                                     prefix='.env-', delete=False) as handle:
        temporary = Path(handle.name)
        handle.write('\n'.join(lines) + '\n')
    try:
        temporary.chmod(0o600)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def credential_value(root: Path, key: str) -> str:
    """Read one credential from .env, treating placeholders as unset."""
    if not key:
        return ''
    value = read_values(root).get(key, '').strip()
    return '' if value.lower() in PLACEHOLDERS else value


def wechat_credentials(root: Path) -> dict:
    """Read publishing credentials from the local .env only."""
    values = read_values(root)
    credentials = {}
    for key, field in CREDENTIALS.items():
        value = values.get(key, '').strip()
        credentials[field] = '' if value.lower() in PLACEHOLDERS else value
    return credentials


def require_wechat_credentials(root: Path) -> dict:
    credentials = wechat_credentials(root)
    if credentials['appid'] and credentials['appsecret']:
        return credentials
    target = root / ENV_NAME
    raise ValueError(
        '微信公众号凭证未配置，无法上传草稿。\n'
        f'  1. 在项目根目录运行：python3 openwrite.py setup（生成 {target}，不覆盖已有文件）\n'
        f'  2. 编辑 {target}，填写 WeChatAppID 和 WeChatAppSecret，可选 WeChatAuthor\n'
        '  获取方式：https://mp.weixin.qq.com → 设置与开发 → 基本配置\n'
        f'  {ENV_NAME} 已被 Git 忽略，只保存在本机；{TEMPLATE_NAME} 仅是占位模板，不要写入真实密钥。'
    )


def xhs_cookie(root: Path) -> str:
    """Read the creator-platform cookie from .env, treating placeholders as unset."""
    value = read_values(root).get('XhsCreatorCookie', '').strip()
    return '' if value.lower() in PLACEHOLDERS else value


def require_xhs_cookie(root: Path) -> str:
    cookie = xhs_cookie(root)
    if cookie:
        return cookie
    target = root / ENV_NAME
    raise ValueError(
        '小红书创作服务平台 Cookie 未配置，无法发布笔记。\n'
        f'  1. 在项目根目录运行：python3 openwrite.py setup（生成 {target}，不覆盖已有文件）\n'
        f'  2. 编辑 {target}，填写 XhsCreatorCookie：浏览器登录 https://creator.xiaohongshu.com 后，\n'
        '     打开开发者工具 → 网络，复制任一创作平台请求的完整 Cookie（需含 a1 与登录凭证）\n'
        '  发布默认「仅自己可见」；公开需显式 --public 授权。Cookie 会过期，失效时重新复制。\n'
        f'  {ENV_NAME} 已被 Git 忽略，只保存在本机；{TEMPLATE_NAME} 仅是占位模板，不要写入真实 Cookie。'
    )
