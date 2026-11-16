"""Platform adapter registry: product specs and skill wiring per publishing platform.

The workflow controller reads this table instead of hard-coding one platform.
Shared order (seven stages, fingerprints, gates) stays platform-neutral; product
shape, limits and skill wiring are data here. Adding a platform means registering
its specs plus its renderer/publisher skills, not copying the controller.

`implemented` is deliberately explicit: a platform may be selectable and persisted
long before its writing/rendering/publishing adapters exist.
"""
from __future__ import annotations

import preferences

WECHAT = 'wechat'
REDNOTE = 'rednote'

REGISTRY = {
    WECHAT: {
        'label': '微信',
        'implemented': True,
        'writers': {
            'blogger': 'wechat-blogger-writer',
            'tech': 'wechat-tech-writer',
            'product': 'wechat-product-manager-writer',
        },
        'renderer': 'wechat-article-formatter',
        'publisher': 'wechat-draft-publisher',
        'publisher_entry': 'publisher.py',
        'publish_implemented': True,
        'format_label': '排版并保存可发布产物',
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
        'credential_keys': ('WeChatAppID', 'WeChatAppSecret', 'WeChatAuthor'),
    },
    REDNOTE: {
        'label': '小红书',
        # P0：写作与卡片产物已实现；上传适配器未实现，publish 仍被拒绝。
        'implemented': True,
        'publish_implemented': False,
        'writers': {'blogger': 'rednote-note-writer'},
        # 方案 A：卡片渲染是图片后端（html），不是独立的第七步排版器。
        'renderer': 'openwrite-images',
        'publisher': 'rednote-publisher',
        'publisher_entry': 'publish_note.py',
        'format_label': '组装并保存可发布产物',
        # 图文形态：笔记文案 + 分页卡片稿 → 3:4 组图，封面即首图。
        'markdown_artifact': 'note.md',
        'rendered_artifact': None,
        'artifacts': ['note.md', 'cards.md'],
        'optional_artifacts': [],
        'cover': {'id': 'cover', 'output': 'xhs-01-cover.png', 'width': 1080, 'height': 1440},
        'content_size': {'width': 1080, 'height': 1440},
        # 张数由内容动态决定；平台单篇上限待核实，先不写死。
        'content_images': {'required': True, 'min': 1, 'max': None},
        'limits': {
            'title_chars': 20, 'title_bytes': None,
            'author_bytes': None, 'digest_bytes': None,
            'cover_bytes': None,
        },
        'checks': {'code_blocks_converted': False, 'local_images_exist': True},
        'author_key': None,
        'credential_keys': ('XhsCreatorCookie',),
        'card_spec': {
            'ratio': '3:4',
            'safe_area': {'side': (72, 96), 'top': (72, 112), 'bottom': (80, 120)},
            'cover_title_chars': 15,
            'page_title_chars': (12, 30),
            'export': 'PNG',
        },
        # 未取得权威来源的项不写入强制 limits，需实测后再补。
        'unverified': ['desc_chars', 'max_images'],
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
    writers = profile['writers']
    if perspective not in writers:
        raise ValueError(f'{profile["label"]}平台尚未适配 {perspective} 写作视角')
    return writers[perspective]


def limits(state: dict) -> dict:
    return for_state(state)['limits']
