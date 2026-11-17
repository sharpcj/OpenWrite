"""Local article artifacts for workflow integration tests; no external calls."""
import layout
from argparse import Namespace
import importlib.util
from pathlib import Path

from PIL import Image
import workflow


def approve_outline(article, title='测试文章', source='candidate'):
    """Record a user-approved title and outline, as the draft stage requires."""
    (layout.path(article, 'outline.md')).write_text(
        f'# 标题与大纲\n\n## 备选标题\n\n1. 激进悬念：{title}？真相没人告诉你\n'
        f'2. 客观中性：{title}\n3. 利益实用：读完搞懂{title}\n\n'
        f'## 大纲\n\n- 开头提出问题\n- 解释与案例\n- 总结建议\n\n## 确认记录\n\n用户选定「{title}」并同意大纲。\n',
        encoding='utf-8')
    candidates = [
        {'title': f'{title}？真相没人告诉你', 'style': '激进悬念'},
        {'title': title, 'style': '客观中性'},
        {'title': f'读完搞懂{title}', 'style': '利益实用'},
    ]
    workflow.write_json(layout.path(article, 'outline.json'), {
        'version': 1, 'candidates': candidates, 'chosen_title': title,
        'title_source': source, 'approved': True,
        'outline_hash': workflow.file_hash(layout.path(article, 'outline.md')),
    })


def seed_body(article, text=None):
    if not (layout.path(article, 'workflow.json')).exists():
        workflow.initialize(article, '测试文章')
    workflow.write_json(layout.path(article, 'sources.json'), {'version': 1, 'sources': [
        {'id': 's1', 'title': '用户资料', 'kind': 'user', 'content': '可验证的测试资料内容'},
    ]})
    workflow.complete(article, 'search')
    (layout.path(article, 'analysis.md')).write_text('# 分析\n\nsource:s1 支持文章中的观点。\n', encoding='utf-8')
    workflow.complete(article, 'analysis')
    approve_outline(article)
    (layout.path(article, 'draft.md')).write_text(text or '# 测试文章\n\n正文内容。\n', encoding='utf-8')
    workflow.complete(article, 'draft')


def image_runtime():
    return workflow.image_runtime()


def plan(article, content=False, anchor='正文内容。'):
    cover = {'id': 'cover', 'role': 'cover', 'output': 'cover.png',
             'width': 60, 'height': 40, 'prompt': '测试封面', 'text': []}
    images = [cover]
    if content:
        images.append({'id': 'diagram', 'role': 'content', 'output': 'diagram.png',
                       'width': 60, 'height': 40, 'prompt': '正文图示',
                       'placement': anchor, 'alt': '图示', 'text': []})
    workflow.write_json(layout.path(article, 'image-requests.json'), {'version': 1, 'images': images})
    return images


def obtain(article, request_id):
    source = article / 'test-source.png'
    Image.new('RGB', (60, 40), 'blue').save(source)
    image_runtime().produce(Namespace(
        article=str(article), id=request_id, backend='file', source=str(source),
        profile=None, timeout=10, fit='exact', overwrite=False,
    ))


def finish_article(article, text=None, content=False, anchor='正文内容。'):
    seed_body(article, text)
    plan(article, content, anchor)
    obtain(article, 'cover')
    workflow.complete(article, 'cover', reviewed=True, note='已检查测试封面')
    if content:
        obtain(article, 'diagram')
    workflow.write_json(layout.path(article, 'content-images.json'), {
        'needed': content, 'reason': '正文需要图示' if content else '文字表达已经足够',
    })
    workflow.complete(article, 'content', reviewed=content, note='已检查测试图示' if content else '')
    workflow.finalize(article)
