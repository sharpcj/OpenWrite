"""Seven-stage progression, invalidation and project command gates."""
from argparse import Namespace
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import workflow
from workflow_fixtures import seed_body, plan, obtain, finish_article, approve_outline

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('workflow_command_test', ROOT / 'openwrite.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-flow-test-')
        self.addCleanup(self.tmp.cleanup)
        self.article = Path(self.tmp.name).resolve()

    def test_only_current_step_can_be_completed(self):
        workflow.initialize(self.article)
        with self.assertRaises(ValueError):
            workflow.complete(self.article, 'draft')
        self.assertEqual(workflow.current(workflow.load(self.article)), 'search')
        workflow.write_json(self.article / 'sources.json', {'version': 1, 'sources': []})
        with self.assertRaises(ValueError):
            workflow.complete(self.article, 'search')

    def test_analysis_must_reference_known_sources_and_title_is_not_body(self):
        seed_body(self.article)
        workflow.reset(self.article, 'analysis')
        (self.article / 'analysis.md').write_text('source:missing 未知来源')
        with self.assertRaises(ValueError):
            workflow.complete(self.article, 'analysis')
        (self.article / 'analysis.md').write_text('source:s1 有依据的判断')
        workflow.complete(self.article, 'analysis')
        (self.article / 'draft.md').write_text('# 只有标题\n')
        with self.assertRaises(ValueError):
            workflow.complete(self.article, 'draft')

    def test_images_are_blocked_before_draft_and_content_waits_for_cover(self):
        workflow.initialize(self.article)
        plan(self.article, content=True)
        with patch.object(cli, 'run_skill') as execute:
            with self.assertRaises(ValueError):
                cli.image_article(Namespace(article=str(self.article), id='cover'))
            execute.assert_not_called()
        seed_body(self.article)
        with self.assertRaises(ValueError):
            workflow.require_image_stage(self.article, 'diagram')
        workflow.require_image_stage(self.article, 'cover')

    def test_cover_completion_requires_actual_artifact_and_review(self):
        seed_body(self.article)
        plan(self.article)
        with self.assertRaises((OSError, ValueError)):
            workflow.complete(self.article, 'cover', reviewed=True, note='检查')
        obtain(self.article, 'cover')
        with self.assertRaises(ValueError):
            workflow.complete(self.article, 'cover')
        with self.assertRaises(ValueError):
            workflow.complete(self.article, 'cover', reviewed=True)
        workflow.complete(self.article, 'cover', reviewed=True, note='文字、构图符合要求')
        self.assertEqual(workflow.current(workflow.load(self.article)), 'content')

    def test_explicit_no_content_decision_allows_finalizing(self):
        seed_body(self.article)
        plan(self.article)
        obtain(self.article, 'cover')
        workflow.complete(self.article, 'cover', reviewed=True, note='封面符合要求')
        with self.assertRaises((OSError, ValueError)):
            workflow.complete(self.article, 'content')
        with self.assertRaises(ValueError):
            workflow.finalize(self.article)
        workflow.write_json(self.article / 'content-images.json', {'needed': False, 'reason': '纯文字足够清楚'})
        workflow.complete(self.article, 'content')
        self.assertFalse((self.article / 'article.md').exists())
        workflow.finalize(self.article)
        self.assertEqual((self.article / 'article.md').read_text(), (self.article / 'draft.md').read_text())
        self.assertEqual(workflow.current(workflow.load(self.article)), 'format')
        with self.assertRaises(ValueError):
            workflow.require_finished(self.article)

    def test_adding_content_request_does_not_expire_reviewed_cover(self):
        seed_body(self.article)
        plan(self.article)
        obtain(self.article, 'cover')
        workflow.complete(self.article, 'cover', reviewed=True, note='已验收封面')
        plan(self.article, content=True)
        self.assertIsNone(workflow.stale_step(self.article, workflow.load(self.article)))
        obtain(self.article, 'diagram')
        workflow.write_json(self.article / 'content-images.json', {'needed': True, 'reason': '需要图示'})
        with self.assertRaises(ValueError):
            workflow.complete(self.article, 'content')
        workflow.complete(self.article, 'content', reviewed=True, note='图示与正文一致')
        workflow.finalize(self.article)
        text = (self.article / 'article.md').read_text()
        self.assertIn('正文内容。\n\n![图示](diagram.png)', text)
        self.assertNotIn('cover.png', text)

    def test_invalid_placement_and_wrong_image_result_cannot_complete(self):
        seed_body(self.article)
        plan(self.article, content=True, anchor='不存在的段落')
        obtain(self.article, 'cover')
        workflow.complete(self.article, 'cover', reviewed=True, note='已检查')
        obtain(self.article, 'diagram')
        workflow.write_json(self.article / 'content-images.json', {'needed': True, 'reason': '需要'})
        with self.assertRaises(ValueError):
            workflow.complete(self.article, 'content', reviewed=True, note='已检查')
        plan(self.article, content=True)
        # Changing the requirement invalidates the previous result fingerprint.
        with self.assertRaises(ValueError):
            workflow.complete(self.article, 'content', reviewed=True, note='已检查')

    def test_modified_upstream_requires_reset_and_preserves_files(self):
        finish_article(self.article)
        old_article = (self.article / 'article.md').read_bytes()
        (self.article / 'draft.md').write_text('# 测试文章\n\n修改后的正文。\n')
        self.assertEqual(workflow.stale_step(self.article, workflow.load(self.article))[0], 'draft')
        with self.assertRaises(ValueError):
            workflow.require_finished(self.article)
        workflow.reset(self.article, 'draft')
        self.assertEqual(workflow.current(workflow.load(self.article)), 'draft')
        self.assertEqual((self.article / 'article.md').read_bytes(), old_article)
        self.assertTrue((self.article / 'cover.png').exists())
        workflow.complete(self.article, 'draft')
        self.assertEqual(workflow.current(workflow.load(self.article)), 'cover')

    def test_modified_sources_invalidates_the_first_step(self):
        seed_body(self.article)
        data = workflow.read_json(self.article / 'sources.json')
        data['sources'][0]['content'] = '资料已经变化'
        workflow.write_json(self.article / 'sources.json', data)
        self.assertEqual(workflow.stale_step(self.article, workflow.load(self.article))[0], 'search')
        with self.assertRaises(ValueError):
            workflow.complete(self.article, 'cover', reviewed=True, note='不应跳过')

    def test_format_and_publish_cannot_run_with_unfinished_workflow(self):
        seed_body(self.article)
        with patch.object(cli, 'run_skill') as execute:
            with self.assertRaises(ValueError):
                cli.format_article(Namespace(article=str(self.article)))
            with self.assertRaises(ValueError):
                cli.publish_article(Namespace(article=str(self.article)))
            execute.assert_not_called()

    def test_publish_rejects_modified_html_and_workflow_reset_invalidates_format(self):
        finish_article(self.article)
        html = self.article / 'article.html'
        html.write_text('<p>排版结果</p>')
        workflow.complete_format(self.article, 'default', True, {})
        workflow.require_publishable(self.article)
        self.assertEqual(workflow.current(workflow.load(self.article)), None)
        html.write_text('<p>未经重新排版的修改</p>')
        with self.assertRaises(ValueError):
            workflow.require_publishable(self.article)
        # Re-formatting after completion replaces the seventh record instead of appending.
        workflow.complete_format(self.article, 'grace', True, {})
        self.assertEqual(len(workflow.load(self.article)['completed']), len(workflow.STEPS))
        workflow.require_publishable(self.article)
        workflow.reset(self.article, 'markdown')
        workflow.finalize(self.article)
        with self.assertRaises(ValueError):
            workflow.require_publishable(self.article)

    def test_placement_cannot_match_only_part_of_a_paragraph(self):
        seed_body(self.article)
        plan(self.article, content=True, anchor='正文')
        workflow.write_json(self.article / 'content-images.json', {'needed': True, 'reason': '需要图示'})
        with self.assertRaises(ValueError):
            workflow.final_text(self.article)

    def test_cli_lifecycle_new_to_final_markdown_and_format(self):
        import shutil
        project = self.article / 'project'
        project.mkdir()
        for name in ('openwrite.py', 'workflow.py', 'preferences.py', 'platforms.py'):
            shutil.copy2(ROOT / name, project / name)
        shutil.copytree(ROOT / 'skills', project / 'skills')

        def run(*args, ok=True):
            result = subprocess.run([sys.executable, '-B', str(project / 'openwrite.py'), *args],
                                    cwd=project, capture_output=True, text=True)
            if ok:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            else:
                self.assertNotEqual(result.returncode, 0)
            return result

        (project / '.env').write_text('WeChat=true\nWriterRole=SelfMediaBlogger\n')
        run('new', 'cli-article', '--title', '命令行测试')
        article = project / 'articles/cli-article'
        location = str(article)
        self.assertFalse((article / 'article.md').exists())
        run('workflow', 'complete', location, '--step', 'analysis', ok=False)
        workflow.write_json(article / 'sources.json', {'version': 1, 'sources': [
            {'id': 's1', 'title': '用户资料', 'kind': 'user', 'content': '测试的实际资料'},
        ]})
        run('workflow', 'complete', location, '--step', 'search')
        (article / 'analysis.md').write_text('source:s1 支持正文观点。')
        run('workflow', 'complete', location, '--step', 'analysis')
        approve_outline(article, title='命令行测试')
        (article / 'draft.md').write_text('# 命令行测试\n\n正文内容。\n')
        run('workflow', 'complete', location, '--step', 'draft')
        plan(article)
        from PIL import Image
        source = self.article / 'source.png'
        Image.new('RGB', (60, 40), 'blue').save(source)
        run('image', location, '--id', 'cover', '--backend', 'file', '--source', str(source))
        run('workflow', 'complete', location, '--step', 'cover', ok=False)
        run('workflow', 'complete', location, '--step', 'cover', '--reviewed', '--note', '已实际检查')
        workflow.write_json(article / 'content-images.json', {'needed': False, 'reason': '无需配图'})
        run('workflow', 'complete', location, '--step', 'content')
        run('workflow', 'finalize', location)
        run('format', location, '--no-preformat')
        self.assertTrue((article / 'article.html').is_file())
        self.assertTrue((article / 'publish-manifest.json').is_file())
        self.assertFalse((article / 'format-state.json').exists())
        self.assertIsNone(workflow.current(workflow.load(article)))
        self.assertEqual(workflow.load(article)['title'], '命令行测试')
        (article / 'draft.md').write_text('# 修改\n\n正文已经修改。\n')
        run('format', location, ok=False)
        status = run('workflow', 'status', location)
        self.assertIn('[已过期] draft', status.stdout)

    def test_status_is_read_only_and_survives_new_process(self):
        seed_body(self.article)
        before = (self.article / 'workflow.json').read_bytes()
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'openwrite.py'),
                                 'workflow', 'status', str(self.article)],
                                cwd=self.article, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('[当前] cover', result.stdout)
        self.assertEqual((self.article / 'workflow.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
