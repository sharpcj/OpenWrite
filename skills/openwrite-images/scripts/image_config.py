#!/usr/bin/env python3
"""Shared configuration for the image capability.

Two layers, one direction of precedence:

- Project-local `.env` (Git-ignored): service addresses and API keys.
  Process environment variables win over `.env` values.
- Skill `config.json` (tracked): model profiles, workflow templates,
  source priority and cover-text layout rules. Never holds secrets.

The `.env` parser mirrors `preferences.parse_env` semantics: plain
KEY=value lines, optional quotes and trailing comments, nothing executed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
from urllib.parse import urlparse

CAPABILITY = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_NAME = '.env'

# Backends understood by produce.py; `file` imports an existing local image
# (host tool output, user-provided art, or an official-doc illustration the
# agent downloaded), `html` renders text-precise cards.
BACKENDS = ('comfyui', 'file', 'html', 'gemini', 'dalle',
            'fal', 'hunyuan', 'pexels', 'pixabay', 'unsplash')
STOCK_BACKENDS = ('pexels', 'pixabay', 'unsplash')
ONLINE_BACKENDS = ('fal', 'hunyuan')
# Keys read from .env / process environment for each optional backend.
BACKEND_KEYS = {
    'fal': ('FAL_KEY', 'FAL_AI_API_KEY'),
    'hunyuan': ('TENCENT_TOKENHUB_API_KEY',),
    'pexels': ('PEXELS_API_KEY',),
    'pixabay': ('PIXABAY_API_KEY',),
    'unsplash': ('UNSPLASH_ACCESS_KEY',),
    'gemini': ('GEMINI_API_KEY', 'GOOGLE_API_KEY'),
    'dalle': ('OPENAI_API_KEY',),
}
DEFAULT_COMFYUI_URL = 'http://localhost:8188'


def parse_env(path: Path) -> dict:
    """Read KEY=value lines as strings; quotes and trailing comments honoured."""
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


def env_values(root: Path = None) -> dict:
    """Values from the project-local .env; absent file means empty config."""
    path = (root or PROJECT_ROOT) / ENV_NAME
    return parse_env(path) if path.is_file() else {}


def setting(key: str, default: str = '', root: Path = None) -> str:
    """Process environment wins over .env; empty values fall back."""
    value = os.environ.get(key) or env_values(root).get(key, '')
    value = value.strip()
    return value or default


def backend_key(backend: str, root: Path = None) -> str:
    """First configured key for a backend; empty string when unconfigured."""
    for key in BACKEND_KEYS.get(backend, ()):
        value = setting(key, root=root)
        if value:
            return value
    return ''


def skill_config() -> dict:
    """Tracked rules from config.json; missing file yields an empty dict."""
    path = CAPABILITY / 'config.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _is_local(url: str) -> bool:
    host = (urlparse(url).hostname or '').lower()
    return host in ('localhost', '127.0.0.1', '::1')


def comfyui_urls(root: Path = None) -> list:
    """Configured ComfyUI addresses, local ones first.

    COMFYUI_SERVER_URL may hold one address or several comma-separated ones
    (local or remote). Legacy COMFYUI_URL / config.json comfyui_url remain
    readable so older setups keep working.
    """
    cfg = skill_config()
    raw = (setting('COMFYUI_SERVER_URL', root=root)
           or setting('COMFYUI_URL', root=root)
           or str(cfg.get('comfyui_url') or '')
           or DEFAULT_COMFYUI_URL)
    urls = [part.strip().rstrip('/') for part in raw.split(',') if part.strip()]
    for url in urls:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            raise ValueError(f'ComfyUI 服务地址不合法：{url}（需含协议与端口，如 http://localhost:8188）')
    # Stable sort: loopback addresses first, configured order otherwise.
    return sorted(dict.fromkeys(urls), key=lambda url: 0 if _is_local(url) else 1)


def source_priority(role: str) -> list:
    """Default fallback order per role; config.json may override."""
    defaults = {
        'cover': ['comfyui', 'fal', 'hunyuan', 'pexels', 'pixabay', 'unsplash'],
        'content': ['file', 'comfyui', 'pexels', 'pixabay', 'unsplash', 'fal', 'hunyuan'],
    }
    configured = (skill_config().get('source_priority') or {}).get(role)
    if isinstance(configured, list) and configured:
        return [name for name in configured if name in BACKENDS]
    return defaults.get(role, defaults['content'])


def online_model(backend: str) -> str:
    defaults = {'fal': 'fal-ai/flux/dev', 'hunyuan': 'hy-image-v3.5-preview'}
    configured = (skill_config().get('online_models') or {}).get(backend)
    return configured or defaults[backend]


def cover_text_defaults() -> dict:
    defaults = {
        'font_candidates': [
            '/System/Library/Fonts/PingFang.ttc',
            '/System/Library/Fonts/STHeiti Medium.ttc',
            '/Library/Fonts/Arial Unicode.ttf',
            '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
            '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',
            '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
            'C:/Windows/Fonts/msyh.ttc',
        ],
        'position': 'bottom-left',
        'color': '#ffffff',
        'scrim': True,
        'margin_ratio': 0.06,
        'title_height_ratio': 0.18,
        'subtitle_height_ratio': 0.10,
    }
    configured = skill_config().get('cover_text')
    if isinstance(configured, dict):
        defaults.update({key: value for key, value in configured.items() if key in defaults})
    return defaults
