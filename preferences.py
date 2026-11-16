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
KNOWN_KEYS = set(PLATFORMS) | set(PERSPECTIVES) | set(CREDENTIALS)
PLACEHOLDERS = {'', 'your_appid', 'your_appid_here', 'your_appsecret', 'your_appsecret_here',
                'your_author', 'your_author_here', 'changeme'}


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
    flags = {}
    for key, value in read_values(root).items():
        if key not in PLATFORMS and key not in PERSPECTIVES:
            continue
        if value.lower() not in ('true', 'false'):
            raise ValueError(f'{ENV_NAME} 中的 {key} 只能为 true 或 false')
        flags[key] = value.lower() == 'true'
    return flags


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
    for name, label, options, explicit, argument in (
        ('platform', '平台', PLATFORMS, platform, '--platform'),
        ('perspective', '写作视角', PERSPECTIVES, perspective, '--perspective'),
    ):
        if explicit is not None:
            result[name] = explicit
            selection_source[name] = 'explicit'
            continue
        enabled = [value for key, value in options.items() if flags.get(key, False)]
        if len(enabled) == 1:
            result[name] = enabled[0]
            selection_source[name] = 'config'
        else:
            reason = '没有唯一启用项' if not enabled else '同时启用了多个选项'
            missing.append(f'{label}{reason}，请向用户明确确认后传入 {argument} ({" / ".join(options.values())})')
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
