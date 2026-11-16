"""Seventh stage: publishable checks, manifest fingerprints and publish gating."""
from argparse import Namespace
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import workflow
from workflow_fixtures import finish_article, seed_body

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('openwrite_publishable_test', ROOT / 'openwrite.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class PublishableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-publishable-')
        self.addCleanup(self.tmp.cleanup)
        self.article = Path(self.tmp.name).resolve()

    def staged(self, html):
        path = self.article / 'staged.html'
        path.write_text(html, encoding='utf-8')
        return path

    def test_format_is_blocked_until_the_first_six_stages_pass(self):
        seed_body(self.article)
        with patch.object(cli, 'run_skill') as execute:
            with self.assertRaises(ValueError):
                cli.format_article(Namespace(article=str(self.article), theme='default', no_preformat=True))
            execute.assert_not_called()

    def test_checks_reject_unpublishable_artifacts(self):
        finish_article(self.article)
        state = workflow.load(self.article)
        workflow.check_publishable(self.article, state, self.staged('<p>正文</p>'))
        for html in ('<pre><code>x</code></pre>', '<img src="missing.png">', '   '):
            with self.subTest(html=html):
                with self.assertRaises(ValueError):
                    workflow.check_publishable(self.article, state, self.staged(html))
        with self.assertRaises(ValueError) as error:
            workflow.check_publishable(self.article, dict(state, title='长' * 65), self.staged('<p>正文</p>'))
        self.assertIn('标题超过', str(error.exception))
        with patch.object(workflow.preferences, 'wechat_credentials',
                          return_value={'appid': '', 'appsecret': '', 'author': '作者' * 20}):
            with self.assertRaises(ValueError) as error:
                workflow.check_publishable(self.article, state, self.staged('<p>正文</p>'))
        self.assertIn('作者名超过', str(error.exception))
        (self.article / 'cover.png').unlink()
        with self.assertRaises(ValueError) as error:
            workflow.check_publishable(self.article, state, self.staged('<p>正文</p>'))
        self.assertIn('缺少封面', str(error.exception))

    def test_failed_checks_preserve_previous_html_and_stage(self):
        finish_article(self.article)
        output = self.article / 'article.html'
        output.write_text('<p>上一次成功的排版</p>', encoding='utf-8')
        workflow.complete_format(self.article, 'default', True, {})
        before = output.read_bytes()
        state_before = workflow.load(self.article)
        # A no-op conversion leaves the staged HTML empty, so the checks must fail.
        with patch.object(cli, 'run_skill', return_value=0):
            with self.assertRaises(ValueError) as error:
                cli.format_article(Namespace(article=str(self.article), theme='grace', no_preformat=True))
        self.assertIn('尚不可发布', str(error.exception))
        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(workflow.load(self.article), state_before)

    def test_manifest_records_metadata_and_reflow_replaces_the_record(self):
        finish_article(self.article)
        (self.article / 'article.html').write_text('<p>正文</p>', encoding='utf-8')
        state = workflow.complete_format(self.article, 'default', True, {'html_chars': 12})
        self.assertIsNone(workflow.current(state))
        manifest = workflow.read_json(self.article / 'publish-manifest.json')
        self.assertEqual((manifest['title'], manifest['theme'], manifest['preformat']), ('测试文章', 'default', True))
        self.assertIn('article.html', manifest['files'])
        self.assertIn('cover.png', manifest['files'])
        workflow.require_publishable(self.article)

        (self.article / 'article.html').write_text('<p>换主题重排</p>', encoding='utf-8')
        state = workflow.complete_format(self.article, 'grace', False, {})
        self.assertEqual(len(state['completed']), len(workflow.STEPS))
        self.assertEqual(state['completed'][-1]['step'], 'format')
        manifest = workflow.read_json(self.article / 'publish-manifest.json')
        self.assertEqual((manifest['theme'], manifest['preformat']), ('grace', False))
        workflow.require_publishable(self.article)

        workflow.reset(self.article, 'format')
        self.assertEqual(workflow.current(workflow.load(self.article)), 'format')
        self.assertTrue((self.article / 'article.html').is_file())

    def test_publish_uses_manifest_metadata_and_rejects_changed_artifacts(self):
        finish_article(self.article)
        (self.article / 'article.html').write_text('<p>正文</p>', encoding='utf-8')
        workflow.complete_format(self.article, 'default', True, {})
        args = Namespace(article=str(self.article), title=None, author=None, digest=None)
        with patch.object(cli, 'run_skill', return_value=0) as execute:
            self.assertEqual(cli.publish_article(args), 0)
        passed = execute.call_args.args
        self.assertEqual(passed[passed.index('--title') + 1], '测试文章')
        self.assertEqual(passed[passed.index('--cover') + 1], str(self.article / 'cover.png'))

        (self.article / 'article.html').write_text('<p>未经重新排版的修改</p>', encoding='utf-8')
        with patch.object(cli, 'run_skill') as execute:
            with self.assertRaises(ValueError):
                cli.publish_article(args)
            execute.assert_not_called()

    def test_publish_metadata_can_be_overridden_explicitly(self):
        finish_article(self.article)
        (self.article / 'article.html').write_text('<p>正文</p>', encoding='utf-8')
        workflow.complete_format(self.article, 'default', True, {})
        args = Namespace(article=str(self.article), title='用户改的标题', author='作者', digest='摘要')
        with patch.object(cli, 'run_skill', return_value=0) as execute:
            self.assertEqual(cli.publish_article(args), 0)
        passed = execute.call_args.args
        self.assertEqual(passed[passed.index('--title') + 1], '用户改的标题')
        self.assertEqual(passed[passed.index('--author') + 1], '作者')
        self.assertEqual(passed[passed.index('--digest') + 1], '摘要')


if __name__ == '__main__':
    unittest.main()
