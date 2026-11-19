"""Rednote P0: card rendering via the html backend, set assembly and upload gate."""
import layout
from argparse import Namespace
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import platforms
import workflow
from workflow_fixtures import approve_outline

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('openwrite_rednote_test', ROOT / 'openwrite.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)

COVER = {'layout': 'cover', 'theme': 'indigo', 'title': '3 个设置让 AI 答得更准',
         'subtitle': '检索增强的最小可用配置', 'bullets': ['开启检索', '限定来源', '要求引用']}
PAGE = {'layout': 'bullets', 'theme': 'indigo', 'title': '为什么它会答错',
        'bullets': ['模型知识有截止时间', '缺少你的私有资料', '没有引用约束']}
TITLE = '3 个设置让 AI 答得更准'


def card_request(identifier, role, output, card, order=None):
    request = {'id': identifier, 'role': role, 'output': output, 'width': 1080, 'height': 1440,
               'prompt': f'卡片：{card["title"]}', 'card': card, 'text': [card['title']]}
    if order is not None:
        request['order'] = order
    return request


def plan(article, pages=1):
    images = [card_request('cover', 'cover', 'xhs-01-cover.png', COVER)]
    for index in range(pages):
        images.append(card_request(f'page{index + 1}', 'content', f'xhs-0{index + 2}-page.png',
                                   PAGE, order=index + 2))
    workflow.write_json(layout.path(article, 'image-requests.json'), {'version': 1, 'images': images})
    return images


def render(article, request_id):
    runtime = workflow.image_runtime()
    return runtime.produce(Namespace(article=str(article), id=request_id, backend='html',
                                     source=None, profile=None, timeout=60, fit='exact',
                                     overwrite=False))


def seed_draft(article):
    workflow.initialize(article, TITLE, 'blogger', 'rednote', {})
    workflow.write_json(layout.path(article, 'sources.json'), {'version': 1, 'sources': [
        {'id': 's1', 'title': '用户资料', 'kind': 'user', 'content': '可验证的测试资料'},
    ]})
    workflow.complete(article, 'search')
    (layout.path(article, 'analysis.md')).write_text('# 分析\n\nsource:s1 支持核心观点。\n', encoding='utf-8')
    workflow.complete(article, 'analysis')
    approve_outline(article, title=TITLE)
    (layout.path(article, 'draft.md')).write_text(
        f'# {TITLE}\n\n之前问它专业问题，三次答案都不一样。改了三个设置后稳定多了。\n\n'
        '话题：AI工具 检索增强 效率\n', encoding='utf-8')
    (layout.path(article, 'cards.md')).write_text(
        '# 卡片稿\n\n## 第 1 张（封面）\n标题：3 个设置让 AI 答得更准\n\n---\n\n'
        '## 第 2 张\n标题：为什么它会答错\n要点：知识截止 / 缺少私有资料 / 没有引用约束\n',
        encoding='utf-8')
    workflow.complete(article, 'draft')


def finish(article, pages=1):
    seed_draft(article)
    plan(article, pages)
    render(article, 'cover')
    workflow.complete(article, 'cover', reviewed=True, note='已检查封面文字与版式')
    for index in range(pages):
        render(article, f'page{index + 1}')
    workflow.write_json(layout.path(article, 'content-images.json'),
                        {'needed': True, 'reason': '卡片承载核心观点'})
    workflow.complete(article, 'content', reviewed=True, note='已逐张检查卡片')
    workflow.finalize(article)


class RednotePipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-rednote-')
        self.addCleanup(self.tmp.cleanup)
        self.article = Path(self.tmp.name).resolve()

    def test_html_backend_renders_exact_card_size(self):
        seed_draft(self.article)
        plan(self.article)
        result = render(self.article, 'cover')
        self.assertEqual(result['status'], 'ready')
        self.assertEqual((result['width'], result['height']), (1080, 1440))
        from PIL import Image
        with Image.open(self.article / 'xhs-01-cover.png') as picture:
            self.assertEqual(picture.size, (1080, 1440))
            self.assertEqual(picture.format, 'PNG')
        workflow.complete(self.article, 'cover', reviewed=True, note='已检查')

    def test_cover_name_and_card_order_are_enforced(self):
        seed_draft(self.article)
        images = plan(self.article)
        images[0]['output'] = 'cover.png'
        workflow.write_json(layout.path(self.article, 'image-requests.json'), {'version': 1, 'images': images})
        with self.assertRaises(ValueError) as error:
            workflow.requests(self.article)
        self.assertIn('xhs-01-cover.png', str(error.exception))
        plan(self.article)
        images = workflow.read_json(layout.path(self.article, 'image-requests.json'))['images']
        del images[1]['order']
        workflow.write_json(layout.path(self.article, 'image-requests.json'), {'version': 1, 'images': images})
        with self.assertRaises(ValueError):
            workflow.requests(self.article)
        images[1]['order'] = 2
        images.append(card_request('dup', 'content', 'xhs-03-dup.png', PAGE, order=2))
        workflow.write_json(layout.path(self.article, 'image-requests.json'), {'version': 1, 'images': images})
        with self.assertRaises(ValueError) as error:
            workflow.requests(self.article)
        self.assertIn('order 不可重复', str(error.exception))

    def test_content_cards_are_required(self):
        seed_draft(self.article)
        workflow.write_json(layout.path(self.article, 'image-requests.json'), {'version': 1, 'images': [
            card_request('cover', 'cover', 'xhs-01-cover.png', COVER),
        ]})
        with self.assertRaises(ValueError) as error:
            workflow.requests(self.article)
        self.assertIn('至少需要 1 张正文卡片', str(error.exception))

    def test_note_assembly_does_not_embed_cards_and_parses_topics(self):
        finish(self.article)
        text = (self.article / 'note.md').read_text(encoding='utf-8')
        self.assertNotIn('![', text)
        self.assertNotIn('.png', text)
        parts = workflow.note_parts(self.article)
        self.assertEqual(parts['title'], TITLE)
        self.assertEqual(parts['topics'], ['AI工具', '检索增强', '效率'])
        self.assertIn('三次答案都不一样', parts['desc'])
        self.assertNotIn('话题', parts['desc'])

    def test_editing_card_copy_expires_the_draft_stage(self):
        finish(self.article)
        self.assertIsNone(workflow.stale_step(self.article, workflow.load(self.article)))
        (layout.path(self.article, 'cards.md')).write_text('# 卡片稿\n\n改了卡片文案。\n', encoding='utf-8')
        self.assertEqual(workflow.stale_step(self.article, workflow.load(self.article))[0], 'draft')

    def test_seventh_stage_assembles_ordered_manifest(self):
        finish(self.article, pages=2)
        self.assertEqual(workflow.current(workflow.load(self.article)), 'format')
        state = workflow.load(self.article)
        checks = workflow.check_publishable(self.article, state)
        self.assertEqual(checks['cards'], 3)
        workflow.complete_format(self.article, 'indigo', False, checks)
        manifest = workflow.read_json(layout.path(self.article, 'publish-manifest.json'))
        self.assertEqual(manifest['platform'], 'rednote')
        self.assertEqual(manifest['images'],
                         ['xhs-01-cover.png', 'xhs-02-page.png', 'xhs-03-page.png'])
        self.assertEqual(manifest['topics'], ['AI工具', '检索增强', '效率'])
        self.assertIn('desc', manifest)
        self.assertIn('cards.md', manifest['files'])
        self.assertIsNone(workflow.current(workflow.load(self.article)))
        workflow.require_publishable(self.article)

    def test_wrong_card_size_and_long_title_are_rejected(self):
        finish(self.article)
        state = workflow.load(self.article)
        from PIL import Image
        Image.new('RGB', (60, 40), 'blue').save(self.article / 'xhs-02-page.png')
        with self.assertRaises(ValueError) as error:
            workflow.check_publishable(self.article, state)
        self.assertIn('尺寸', str(error.exception))
        fresh = self.article / 'long-title'
        fresh.mkdir()
        finish(fresh)
        long_state = dict(workflow.load(fresh), title='长' * 21)
        with self.assertRaises(ValueError) as error:
            workflow.check_publishable(fresh, long_state)
        self.assertIn('标题超过 20 字符', str(error.exception))

    def test_publish_dispatches_card_set_to_adapter(self):
        finish(self.article)
        workflow.complete_format(self.article, 'indigo', False,
                                 workflow.check_publishable(self.article, workflow.load(self.article)))
        args = Namespace(article=str(self.article), title=None, author=None, digest=None,
                         public=False, dry_run=False, headed=False)
        with patch.object(cli, 'run_skill', return_value=0) as execute:
            self.assertEqual(cli.publish_article(args), 0)
        name, entry, *arguments = execute.call_args.args
        self.assertEqual((name, entry), ('rednote-publisher', 'publish_note.py'))
        self.assertIn('--desc', arguments)
        self.assertNotIn('--public', arguments)

    def test_cli_seventh_stage_reports_publish_ready(self):
        project = self.article / 'project'
        project.mkdir()
        for name in ('openwrite.py', 'workflow.py', 'preferences.py', 'platforms.py', 'layout.py',
                     'writer_roles.py'):
            shutil.copy2(ROOT / name, project / name)
        shutil.copytree(ROOT / 'writer_roles', project / 'writer_roles')
        shutil.copytree(ROOT / 'skills', project / 'skills')
        (project / 'openwrite.yaml').write_text('wechat:\n  accounts:\n    主号: {}\n', encoding='utf-8')
        article = project / 'articles/note'
        article.mkdir(parents=True)
        finish(article)
        result = subprocess.run([sys.executable, '-B', str(project / 'openwrite.py'),
                                 'format', str(article)], cwd=project, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('已组装可发布产物', result.stdout)
        self.assertIn('上传仍需用户明确确认', result.stdout)
        status = subprocess.run([sys.executable, '-B', str(project / 'openwrite.py'),
                                 'workflow', 'status', str(article)], cwd=project,
                                capture_output=True, text=True)
        self.assertIn('[已完成] format — 生成可发布交付件', status.stdout)


if __name__ == '__main__':
    unittest.main()
