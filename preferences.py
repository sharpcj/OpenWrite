"""Project-local defaults; explicit task choices win and are persisted by the caller.

Runtime configuration is read only from the local `openwrite.yaml` (Git-ignored,
mode 600). `openwrite.example.yaml` is a tracked sample used solely by
`init_config` to create it; it never participates in resolution. The file is
parsed with yaml.safe_load and validated against a fixed schema; nothing in it
is executed or expanded.

Structure (four merge levels, later wins):

    defaults -> wechat/rednote -> accounts.<name> -> task snapshot

`defaults` holds writer_role and outline_approval. Each platform keeps a map of
accounts: WeChat accounts may override writer_role/outline_approval, define
cover styles and hold publishing credentials; Rednote accounts hold the creator
cookie. A platform is enabled when it has at least one account and is not
explicitly disabled. Image-source addresses and keys live in image_sources.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

import yaml

PLATFORMS = {'WeChat': 'wechat', 'Rednote': 'rednote'}
PERSPECTIVES = {'SelfMediaBlogger': 'blogger', 'TechWriter': 'tech', 'ProductManager': 'product'}
PLATFORM_LABELS = {'wechat': '微信', 'rednote': '小红书'}
PERSPECTIVE_LABELS = {'blogger': '自媒体博主', 'tech': '技术作者', 'product': '产品经理'}

TEMPLATE_NAME = 'openwrite.example.yaml'
CONFIG_NAME = 'openwrite.yaml'
DEFAULT_WRITER_ROLE = 'blogger'
COVER_DIMENSIONS = ('theme', 'layout', 'visual_style', 'color_tone')
# Account fields per platform; unknown fields are rejected instead of ignored.
ACCOUNT_FIELDS = {
    'wechat': {'name', 'app_id', 'app_secret', 'author', 'writer_role', 'outline_approval', 'cover'},
    'rednote': {'name', 'cookie'},
}
PLATFORM_FIELDS = {'enabled', 'default_account', 'accounts'}
DEFAULT_FIELDS = {'writer_role', 'outline_approval'}
# Image-source addresses and keys; consumed by skills/openwrite-images.
IMAGE_FIELDS = {'comfyui_server_url', 'fal_key', 'fal_ai_api_key', 'tencent_tokenhub_api_key',
                'pexels_api_key', 'pixabay_api_key', 'unsplash_access_key',
                'gemini_api_key', 'google_api_key', 'openai_api_key'}
PLACEHOLDERS = {'', 'your_appid', 'your_appid_here', 'your_appsecret', 'your_appsecret_here',
                'your_author', 'your_author_here', 'changeme',
                'your_cookie', 'your_cookie_here', 'your_xhs_cookie_here'}


class ChoiceRequired(ValueError):
    """The agent must obtain an explicit user choice instead of guessing."""


def _normalize_role(raw, where: str) -> str:
    """Accept perspective ids and legacy role labels, case-insensitively."""
    text = str(raw).strip()
    for label, perspective in PERSPECTIVES.items():
        if text.casefold() in (label.casefold(), perspective):
            return perspective
    raise ValueError(f'{where} 的 writer_role 只能为 {" / ".join(PERSPECTIVES.values())}'
                     f'（或 {" / ".join(PERSPECTIVES)}，当前：{text}）')


def _string(value, where: str) -> str:
    if value is None:
        return ''
    if not isinstance(value, str):
        raise ValueError(f'{where} 必须是字符串（当前：{value!r}）')
    return value


def _boolean(value, where: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f'{where} 只能为 true 或 false（当前：{value!r}）')
    return value


def validate_cover_style(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) - set(COVER_DIMENSIONS):
        raise ValueError('封面样式仅包含 theme、layout、visual_style、color_tone')
    normalized = {}
    for key, text in value.items():
        if not isinstance(text, str) or not text.strip() or len(text) > 300 or '\n' in text or '\r' in text:
            raise ValueError(f'封面样式 {key} 必须为非空单行描述（不超过 300 字）')
        normalized[key] = text.strip()
    return normalized


def _validate(data, name: str) -> dict:
    """Check the fixed schema; return a normalized copy with role ids resolved."""
    if not isinstance(data, dict):
        raise ValueError(f'{name} 顶层必须是映射（defaults / wechat / rednote / image_sources）')
    unknown = set(data) - {'defaults', 'wechat', 'rednote', 'image_sources'}
    if unknown:
        raise ValueError(f'{name} 含未知配置节：{"、".join(sorted(unknown))}')
    config = {}
    defaults = data.get('defaults') or {}
    if not isinstance(defaults, dict) or set(defaults) - DEFAULT_FIELDS:
        raise ValueError(f'{name} 的 defaults 仅支持 writer_role 与 outline_approval')
    config['defaults'] = {}
    if defaults.get('writer_role') not in (None, ''):
        config['defaults']['writer_role'] = _normalize_role(defaults['writer_role'], f'{name} defaults')
    if 'outline_approval' in defaults:
        config['defaults']['outline_approval'] = _boolean(defaults['outline_approval'],
                                                         f'{name} defaults.outline_approval')
    for label, platform in PLATFORMS.items():
        section = data.get(platform)
        if section is None:
            continue
        where = f'{name} {platform}'
        if not isinstance(section, dict) or set(section) - PLATFORM_FIELDS:
            raise ValueError(f'{where} 仅支持 enabled、default_account 与 accounts')
        accounts = section.get('accounts') or {}
        if not isinstance(accounts, dict):
            raise ValueError(f'{where}.accounts 必须是「账号名: 配置」映射')
        normalized = {}
        for account, fields in accounts.items():
            if not isinstance(account, str) or not account.strip() or '\n' in account:
                raise ValueError(f'{where}.accounts 的账号名必须为非空单行字符串')
            account = account.strip()
            if account in normalized:
                raise ValueError(f'{where}.accounts 中账号 {account} 重复配置')
            if not isinstance(fields, dict) or set(fields) - ACCOUNT_FIELDS[platform]:
                raise ValueError(f'{where}.accounts.{account} 含未知字段；'
                                 f'可用：{"、".join(sorted(ACCOUNT_FIELDS[platform]))}')
            entry = {}
            for key, value in fields.items():
                spot = f'{where}.accounts.{account}.{key}'
                if key == 'outline_approval':
                    entry[key] = _boolean(value, spot)
                elif key == 'writer_role':
                    entry[key] = _normalize_role(value, spot)
                elif key == 'cover':
                    entry[key] = validate_cover_style(value or {})
                else:
                    entry[key] = _string(value, spot)
            normalized[account] = entry
        enabled = _boolean(section.get('enabled', True), f'{where}.enabled')
        default_account = _string(section.get('default_account'), f'{where}.default_account').strip()
        if default_account and default_account not in normalized:
            raise ValueError(f'{where}.default_account 指向不存在的账号：{default_account}')
        config[platform] = {'enabled': enabled, 'default_account': default_account,
                            'accounts': normalized}
    sources = data.get('image_sources') or {}
    if not isinstance(sources, dict) or set(sources) - IMAGE_FIELDS:
        raise ValueError(f'{name} 的 image_sources 含未知字段；可用：{"、".join(sorted(IMAGE_FIELDS))}')
    config['image_sources'] = {key: _string(value, f'{name} image_sources.{key}')
                               for key, value in sources.items()}
    return config


def read_config(root: Path) -> dict:
    """Read and validate the local openwrite.yaml only; the template is never used."""
    path = root / CONFIG_NAME
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding='utf-8-sig'))
    except yaml.YAMLError as exc:
        raise ValueError(f'{CONFIG_NAME} 解析失败：{exc}') from exc
    return _validate(data if data is not None else {}, CONFIG_NAME)


def enabled_platforms(root: Path) -> list:
    """A platform is enabled when it has accounts and is not explicitly disabled."""
    config = read_config(root)
    return [platform for label, platform in PLATFORMS.items()
            if (config.get(platform) or {}).get('enabled', True)
            and (config.get(platform) or {}).get('accounts')]


def _accounts(root: Path, platform: str) -> dict:
    return (read_config(root).get(platform) or {}).get('accounts', {})


def _default_account(section: dict, accounts: dict):
    if len(accounts) == 1:
        return next(iter(accounts))
    default = section.get('default_account')
    return default if default in accounts else None


def choose_account(root: Path, platform: str, account=None):
    """Explicit account > the only account > default_account > ask the user."""
    section = read_config(root).get(platform) or {}
    accounts = section.get('accounts', {})
    label = PLATFORM_LABELS.get(platform, platform)
    if account is not None:
        if account not in accounts:
            raise ValueError(f'未知{label}账号：{account}（可用：{"、".join(accounts) or "无"}）')
        return account
    if not accounts:
        return None
    chosen = _default_account(section, accounts)
    if chosen:
        return chosen
    raise ChoiceRequired(f'{label}配置了多个账号且未指定 default_account，'
                         f'请向用户明确确认后传入 --account（{" / ".join(accounts)}）')


def writer_role(root: Path, platform=None, account=None) -> tuple:
    """Resolve the perspective: WeChat account override > defaults > blogger."""
    config = read_config(root)
    if platform == 'wechat' and account:
        override = ((config.get('wechat') or {}).get('accounts', {}).get(account) or {}).get('writer_role')
        if override:
            return override, 'config'
    configured = (config.get('defaults') or {}).get('writer_role')
    if configured:
        return configured, 'config'
    return DEFAULT_WRITER_ROLE, 'default'


def outline_approval(root: Path, platform=None, account=None) -> bool:
    """WeChat account override > defaults > enabled."""
    config = read_config(root)
    if platform == 'wechat' and account:
        override = ((config.get('wechat') or {}).get('accounts', {}).get(account) or {}).get('outline_approval')
        if override is not None:
            return override
    return (config.get('defaults') or {}).get('outline_approval', True)


def cover_style(root: Path, layout=None, visual_style=None, color_tone=None, account=None, theme=None) -> dict:
    """Account cover defaults merged with explicit per-task dimensions.

    `theme` selects a cover-designer preset (name or alias); `layout` remains for
    custom layouts / backward compatibility. visual_style/color_tone override.
    """
    name = choose_account(root, 'wechat', account)
    configured = ((_accounts(root, 'wechat').get(name) or {}).get('cover') or {}) if name else {}
    supplied = dict(theme=theme, layout=layout, visual_style=visual_style, color_tone=color_tone)
    chosen = {dimension: supplied[dimension] if supplied[dimension] is not None
              else configured.get(dimension) for dimension in COVER_DIMENSIONS}
    return validate_cover_style({key: value for key, value in chosen.items() if value})


def resolve(root: Path, platform=None, perspective=None, account=None) -> dict:
    for label, supplied, choices in [('平台', platform, PLATFORM_LABELS),
                                     ('写作视角', perspective, PERSPECTIVE_LABELS)]:
        if supplied is not None and supplied not in choices:
            raise ValueError(f'未知{label}：{supplied}')
    result, selection_source, missing = {}, {}, []
    if platform is None and account is not None:
        owners = [value for label, value in PLATFORMS.items() if account in _accounts(root, value)]
        if len(owners) == 1:
            platform = owners[0]
        elif not owners:
            raise ValueError(f'未知账号：{account}（任何平台下都不存在）')
        else:
            missing.append(f'账号 {account} 在多个平台下同名，请同时传入 --platform 明确平台')
    if platform is not None:
        result['platform'] = platform
        selection_source['platform'] = 'explicit'
    else:
        enabled = enabled_platforms(root)
        if len(enabled) == 1:
            result['platform'] = enabled[0]
            selection_source['platform'] = 'config'
        else:
            reason = '没有唯一启用项' if not enabled else '同时启用了多个选项'
            missing.append(f'平台{reason}，请向用户明确确认后传入 --platform ({" / ".join(PLATFORMS.values())})')
    if 'platform' in result:
        chosen = choose_account(root, result['platform'], account)
        if chosen is not None:
            result['account'] = chosen
            selection_source['account'] = 'explicit' if account is not None else 'config'
    if perspective is not None:
        result['perspective'] = perspective
        selection_source['perspective'] = 'explicit'
    else:
        result['perspective'], selection_source['perspective'] = writer_role(
            root, result.get('platform'), result.get('account'))
    if missing:
        raise ChoiceRequired('；'.join(missing))
    result['selection_source'] = selection_source
    return result


def task_platform(state: dict) -> str:
    # Legacy tasks were WeChat-only; never re-read current defaults for existing work.
    return state.get('platform', 'wechat')


def task_perspective(state: dict) -> str:
    return state.get('perspective', state.get('type', 'tech'))


def task_account(state: dict):
    return state.get('account')


def init_config(root: Path) -> tuple:
    """Copy the template to a local openwrite.yaml once; never overwrite existing values."""
    template, target = root / TEMPLATE_NAME, root / CONFIG_NAME
    if os.path.lexists(target):
        if target.is_symlink():
            raise ValueError(f'{CONFIG_NAME} 不能是符号链接')
        return target, False
    if not template.is_file():
        raise ValueError(f'缺少配置模板：{template}')
    target.write_text(template.read_text(encoding='utf-8'), encoding='utf-8')
    target.chmod(0o600)
    return target, True


def _yaml_scalar(value: str) -> str:
    # A JSON string is also a valid double-quoted YAML scalar.
    return json.dumps(value, ensure_ascii=False)


def set_account_author(root: Path, account: str, author: str) -> Path:
    """Update one WeChat account's author in place, keeping comments and layout."""
    config = read_config(root)
    accounts = (config.get('wechat') or {}).get('accounts', {})
    if account not in accounts:
        raise ValueError(f'未知微信账号：{account}')
    target = root / CONFIG_NAME
    lines = target.read_text(encoding='utf-8').splitlines()
    # Locate wechat: -> accounts: -> <account>: by indentation, then edit author.
    index = _find_key(lines, 'wechat', 0)
    index = _find_key(lines, 'accounts', 2, start=index + 1)
    index = _find_account(lines, account, start=index + 1)
    end = index + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() and not line.startswith(' ' * 6):
            break
        end += 1
    for position in range(index + 1, end):
        if lines[position].strip().startswith('author:'):
            lines[position] = ' ' * 6 + 'author: ' + _yaml_scalar(author)
            break
    else:
        lines.insert(end, ' ' * 6 + 'author: ' + _yaml_scalar(author))
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=root,
                                     prefix='openwrite-config-', delete=False) as handle:
        temporary = Path(handle.name)
        handle.write('\n'.join(lines) + '\n')
    try:
        temporary.chmod(0o600)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def _find_key(lines: list, key: str, indent: int, start: int = 0) -> int:
    prefix = ' ' * indent
    for index in range(start, len(lines)):
        line = lines[index]
        if line.startswith(prefix) and not line.startswith(prefix + ' ') \
                and line.strip() == f'{key}:':
            return index
    raise ValueError(f'{CONFIG_NAME} 中找不到 {key} 配置节')


def _find_account(lines: list, account: str, start: int) -> int:
    prefix = ' ' * 4
    candidates = (f'{account}:', f'{_yaml_scalar(account)}:')
    for index in range(start, len(lines)):
        line = lines[index]
        if line.startswith(prefix) and not line.startswith(prefix + ' ') \
                and line.strip() in candidates:
            return index
    raise ValueError(f'{CONFIG_NAME} 中找不到微信账号 {account}')


def _clean(value: str) -> str:
    value = (value or '').strip()
    return '' if value.lower() in PLACEHOLDERS else value


def credential_value(root: Path, key: str, account=None) -> str:
    """Read the manifest author for a WeChat account; ambiguity yields no author."""
    if key != 'WeChatAuthor':
        return ''
    section = read_config(root).get('wechat') or {}
    accounts = section.get('accounts', {})
    name = account if account in accounts else _default_account(section, accounts)
    if not name:
        return ''
    return _clean(accounts[name].get('author', ''))


def wechat_credentials(root: Path, account=None) -> dict:
    """Read publishing credentials for one WeChat account."""
    name = choose_account(root, 'wechat', account)
    fields = _accounts(root, 'wechat').get(name) or {}
    return {'appid': _clean(fields.get('app_id', '')),
            'appsecret': _clean(fields.get('app_secret', '')),
            'author': _clean(fields.get('author', ''))}


def require_wechat_credentials(root: Path, account=None) -> dict:
    credentials = wechat_credentials(root, account)
    if credentials['appid'] and credentials['appsecret']:
        return credentials
    target = root / CONFIG_NAME
    raise ValueError(
        '微信公众号凭证未配置，无法上传草稿。\n'
        f'  1. 在项目根目录运行：.venv/bin/python openwrite.py setup（生成 {target}，不覆盖已有文件）\n'
        f'  2. 编辑 {target}，在 wechat.accounts.<账号名> 下填写 app_id 和 app_secret，可选 author\n'
        '  获取方式：https://mp.weixin.qq.com → 设置与开发 → 基本配置\n'
        f'  {CONFIG_NAME} 已被 Git 忽略，只保存在本机；{TEMPLATE_NAME} 仅是占位模板，不要写入真实密钥。'
    )


def xhs_cookie(root: Path, account=None) -> str:
    """Read the creator-platform cookie for one Rednote account."""
    name = choose_account(root, 'rednote', account)
    fields = _accounts(root, 'rednote').get(name) or {}
    return _clean(fields.get('cookie', ''))


def require_xhs_cookie(root: Path, account=None) -> str:
    cookie = xhs_cookie(root, account)
    if cookie:
        return cookie
    target = root / CONFIG_NAME
    raise ValueError(
        '小红书创作服务平台 Cookie 未配置，无法发布笔记。\n'
        f'  1. 在项目根目录运行：.venv/bin/python openwrite.py setup（生成 {target}，不覆盖已有文件）\n'
        f'  2. 编辑 {target}，在 rednote.accounts.<账号名> 下填写 cookie：浏览器登录 https://creator.xiaohongshu.com 后，\n'
        '     打开开发者工具 → 网络，复制任一创作平台请求的完整 Cookie（需含 a1 与登录凭证）\n'
        '  发布默认「仅自己可见」；公开需显式 --public 授权。Cookie 会过期，失效时重新复制。\n'
        f'  {CONFIG_NAME} 已被 Git 忽略，只保存在本机；{TEMPLATE_NAME} 仅是占位模板，不要写入真实 Cookie。'
    )


def image_values(root: Path) -> dict:
    """Image-source addresses and keys from the local config (snake_case fields)."""
    return read_config(root).get('image_sources', {})
