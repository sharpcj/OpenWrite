"""Platform adapter registry: product specs and skill wiring per publishing platform.

The workflow controller reads this table instead of hard-coding one platform.
Shared order (seven stages, fingerprints, gates) stays platform-neutral; product
shape and limits are data here. Writing-skill wiring lives in the writer role
presets (``writer_roles/*.yaml``), so adding a perspective is a data change.
Adding a platform means registering its specs plus its renderer/publisher
skills, not copying the controller.

`implemented` is deliberately explicit: a platform may be selectable and persisted
long before its writing/rendering/publishing adapters exist.
"""
from __future__ import annotations

import preferences
import writer_roles

WECHAT = 'wechat'
REDNOTE = 'rednote'

REGISTRY = {
    WECHAT: {
        'label': '微信',
        'implemented': True,
        'renderer': 'wechat-article-formatter',
        'publisher': 'wechat-draft-publisher',
        'publisher_entry': 'publisher.py',
        'publish_implemented': True,
        'format_label': '生成可发布交付件',
        # 长文形态：Markdown 整合后转 inline-style HTML。
        'markdown_artifact': 'article.md',
        'rendered_artifact': 'article.html',
        'artifacts': ['article.md', 'article.html', 'cover.png'],
        'optional_artifacts': ['closing.md'],
        'cover': {'id': 'cover', 'output': 'cover.png', 'width': 1024, 'height': 432},
        'content_size': {'width': 1024, 'height': 768},
        # 正文配图可选，可以为零张，但必须记录决策与理由。
        'content_images': {'required': False, 'min': 0, 'max': None},
        'limits': {
            'title_chars': 64, 'title_bytes': 192,
            'author_bytes': 20, 'digest_bytes': 120,
            'cover_bytes': 2 * 1024 * 1024,
        },
        'checks': {'code_blocks_converted': True, 'local_images_exist': True},
        'author_key': 'WeChatAuthor',
        'credential_keys': ('app_id', 'app_secret', 'author'),
    },
    REDNOTE: {
        'label': '小红书',
        # P1：写作、卡片产物与发布适配器均已实现；发布默认仅自己可见。
        'implemented': True,
        'publish_implemented': True,
        # 方案 A：卡片渲染是图片后端（html），不是独立的第七步排版器。
        'renderer': 'openwrite-images',
        'publisher': 'rednote-publisher',
        'publisher_entry': 'publish_note.py',
        'format_label': '生成可发布交付件',
        # 图文形态：笔记文案 + 分页卡片稿 → 3:4 组图，封面即首图。
        'markdown_artifact': 'note.md',
        'rendered_artifact': None,
        'artifacts': ['note.md', 'cards.md'],
        'optional_artifacts': [],
        'cover': {'id': 'cover', 'output': 'xhs-01-cover.png', 'width': 1080, 'height': 1440},
        'content_size': {'width': 1080, 'height': 1440},
        # 张数由内容动态决定；封面 + 内容合计不超过平台单篇 18 张上限。
        'content_images': {'required': True, 'min': 1, 'max': 17},
        'limits': {
            'title_chars': 20, 'title_bytes': None,
            'author_bytes': None, 'digest_bytes': None,
            # 常规图文笔记：正文 ≤1000 字、单篇 ≤18 张图（多个公开来源一致；
            # 「长文笔记」6000 字为另一内测功能，不适用本组图形态）。
            'desc_chars': 1000, 'max_images': 18,
            'cover_bytes': None,
        },
        'checks': {'code_blocks_converted': False, 'local_images_exist': True},
        'author_key': None,
        'credential_keys': ('cookie',),
        'card_spec': {
            'ratio': '3:4',
            'safe_area': {'side': (72, 96), 'top': (72, 112), 'bottom': (80, 120)},
            'cover_title_chars': 15,
            'page_title_chars': (12, 30),
            'export': 'PNG',
        },
        'unverified': [],
    },
}


def spec(platform: str) -> dict:
    if platform not in REGISTRY:
        raise ValueError(f'未知平台：{platform}')
    return REGISTRY[platform]


def for_state(state: dict) -> dict:
    return spec(preferences.task_platform(state))


def require_pipeline(state: dict) -> dict:
    """Reject platforms whose writing/format adapters do not exist yet."""
    profile = for_state(state)
    if not profile['implemented']:
        raise ValueError(f'已保存{profile["label"]}平台选择，但{profile["label"]}创作与发布适配尚未实现；'
                         '不能使用当前七步流程继续')
    return profile


def require_publish_adapter(state: dict) -> dict:
    """Publishing needs its own adapter; a publishable artifact is not an upload path."""
    profile = require_pipeline(state)
    if not profile.get('publish_implemented'):
        raise ValueError(f'{profile["label"]}可发布产物已就绪，但上传适配器尚未实现；'
                         '请手动发布，或等待发布适配器接入')
    return profile


def step_labels(state: dict) -> tuple:
    """Shared stage order, platform-specific wording for the seventh stage."""
    from workflow import LABELS
    return LABELS[:-1] + (for_state(state)['format_label'],)


def writer_skill(state: dict) -> str:
    profile = for_state(state)
    perspective = preferences.task_perspective(state)
    role = writer_roles.load_role(perspective)
    skill = role['skills'].get(preferences.task_platform(state))
    if not skill:
        raise ValueError(f'{profile["label"]}平台尚未适配 {perspective} 写作视角')
    return skill


def limits(state: dict) -> dict:
    return for_state(state)['limits']
