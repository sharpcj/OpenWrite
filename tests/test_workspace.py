"""Checks for project-local workspaces and command integration, without remote calls."""
import layout
import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from argparse import Namespace

import workflow
from workflow_fixtures import finish_article

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('openwrite_workspace', ROOT / 'openwrite.py')
workspace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workspace)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-test-')
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name).resolve()
        (self.directory / '.env').write_text('WeChat=true\nWriterRole=SelfMediaBlogger\n')

    def test_new_article_is_local_and_existing_work_is_preserved(self):
        args = Namespace(name='产品文章', title='一个主题', type='product')
        with patch.object(workspace, 'ROOT', self.directory), redirect_stdout(io.StringIO()):
            self.assertEqual(workspace.new_article(args), 0)
            article = self.directory / 'articles/产品文章'
            self.assertEqual((layout.path(article, 'draft.md')).read_text(), '# 一个主题\n')
            self.assertFalse((article / 'article.md').exists())
            self.assertEqual(workflow.current(workflow.load(article)), 'search')
            self.assertIn('产品经理', (layout.path(article, 'brief.md')).read_text())
            (layout.path(article, 'draft.md')).write_text('已编辑的正文')
            with self.assertRaises(FileExistsError):
                workspace.new_article(args)
            self.assertEqual((layout.path(article, 'draft.md')).read_text(), '已编辑的正文')

    def test_new_article_rejects_path_traversal(self):
        with patch.object(workspace, 'ROOT', self.directory):
            for name in ('../outside', '/absolute', 'a/b', '..'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    workspace.new_article(Namespace(name=name, title=None, type='tech'))
        self.assertFalse((self.directory / 'articles').exists())

    def test_cli_finds_project_resources_from_another_working_directory(self):
        result = subprocess.run(
            [sys.executable, '-B', str(ROOT / 'openwrite.py'), 'doctor'],
            cwd=self.directory, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('OK  Skill wechat-tech-writer', result.stdout)
        self.assertIn('未连接 ComfyUI', result.stdout)

    def test_format_uses_moved_skills_and_keeps_images_and_code(self):
        article = self.directory / 'article with spaces'
        article.mkdir()
        finish_article(article,
            '# 测试文章\n\n## 小节\n\n正文\n\n```python\nprint("hello")\n```\n',
            content=True, anchor='正文')
        for theme in ('default', 'grace', 'modern', 'simple'):
            with self.subTest(theme=theme):
                result = subprocess.run(
                    [sys.executable, '-B', str(ROOT / 'openwrite.py'), 'format', str(article),
                     '--theme', theme, '--no-preformat'],
                    cwd=self.directory, capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                html = (article / 'article.html').read_text()
                self.assertNotIn('<h1', html)
                self.assertNotIn('<pre', html)
                self.assertIn('src="diagram.png"', html)
                self.assertIn('print(&quot;hello&quot;)', html)

    def test_failed_format_preserves_previous_html(self):
        finish_article(self.directory)
        output = self.directory / 'article.html'
        output.write_text('previous successful HTML')
        result = workspace.format_article(Namespace(
            article=str(self.directory), theme='nonexistent-theme', no_preformat=True,
        ))
        self.assertNotEqual(result, 0)
        self.assertEqual(output.read_text(), 'previous successful HTML')

    def test_publish_requires_cover_before_invoking_remote_script(self):
        finish_article(self.directory)
        (self.directory / 'cover.png').unlink()
        args = Namespace(article=str(self.directory), title='标题', author=None, digest=None,
                         public=False, dry_run=False, headed=False)
        with patch.object(workspace, 'run_skill') as execute:
            with self.assertRaises(ValueError):
                workspace.publish_article(args)
            execute.assert_not_called()

    def test_publish_targets_explicit_article_and_forwards_metadata(self):
        finish_article(self.directory)
        (self.directory / 'article.html').write_text('<p>正文</p>')
        workflow.complete_format(self.directory, 'default', True, {})
        args = Namespace(article=str(self.directory), title='指定标题', author='作者', digest='摘要',
                         public=False, dry_run=False, headed=False)
        with patch.object(workspace, 'run_skill', return_value=0) as execute:
            self.assertEqual(workspace.publish_article(args), 0)
        passed = execute.call_args.args
        self.assertEqual(passed[:2], ('wechat-draft-publisher', 'publisher.py'))
        self.assertEqual(passed[passed.index('--content') + 1], str(self.directory / 'article.html'))
        self.assertEqual(passed[passed.index('--cover') + 1], str(self.directory / 'cover.png'))
        self.assertEqual(passed[passed.index('--author') + 1], '作者')


if __name__ == '__main__':
    unittest.main()
