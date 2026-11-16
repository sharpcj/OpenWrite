"""Rednote P1: publish adapter gates, dry-run, cookie handling and UI flow.

The UI flow runs against a local fixture page (tests/fixtures) through real
Playwright + Chromium, so the automation is exercised end-to-end without
touching the live platform or needing a real account.
"""
from argparse import Namespace
import http.server
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import workflow
from test_rednote import TITLE, finish, plan

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / 'fixtures'
COOKIE = 'a1=test-a1; web_session=test-session'

spec = importlib.util.spec_from_file_location(
    'openwrite_rednote_publish_test', ROOT / 'skills/rednote-publisher/publish_note.py')
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)

spec = importlib.util.spec_from_file_location('openwrite_rednote_cli_test', ROOT / 'openwrite.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class FixtureHandler(http.server.BaseHTTPRequestHandler):
    """Serve the mock publish page at the real publish path."""

    def do_GET(self):
        if self.path.split('?')[0] == '/publish/publish':
            body = (FIXTURES / 'xhs_publish_fixture.html').read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def log_message(self, *args):
        pass


class PublishNoteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-rednote-publish-')
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name).resolve()
        shutil.copy2(ROOT / 'preferences.py', self.project / 'preferences.py')
        (self.project / '.env').write_text(f'XhsCreatorCookie="{COOKIE}"\n', encoding='utf-8')
        self.article = self.project / 'article'
        self.article.mkdir()
        from PIL import Image
        for name in ('xhs-01-cover.png', 'xhs-02-page.png'):
            Image.new('RGB', (1080, 1440), 'indigo').save(self.article / name)
        self.images = [str(self.article / 'xhs-01-cover.png'), str(self.article / 'xhs-02-page.png')]

    def run_main(self, *extra):
        return publisher.main(['--title', TITLE, '--desc', '改了三个设置后稳定多了。',
                               '--images', *self.images, '--project-root', str(self.project),
                               '--artifact-dir', str(self.article), *extra])

    def test_dry_run_validates_without_cookie_or_browser(self):
        (self.project / '.env').unlink()
        with patch.object(publisher, 'RednotePublisher') as runtime:
            code = self.run_main('--dry-run')
        runtime.assert_not_called()
        self.assertEqual(code, 0)

    def test_dry_run_rejects_invalid_input(self):
        self.assertNotEqual(self.run_main('--dry-run', '--title', '长' * 21), 0)
        self.assertNotEqual(self.run_main('--dry-run', '--images', str(self.article / 'missing.png')), 0)
        self.assertNotEqual(self.run_main('--dry-run', '--topics', '#带井号'), 0)

    def test_publish_requires_cookie_before_launching_browser(self):
        (self.project / '.env').unlink()
        with patch('playwright.sync_api.sync_playwright') as browser:
            code = self.run_main()
        self.assertNotEqual(code, 0)
        browser.assert_not_called()

    def test_cookie_validation_requires_a1_and_session(self):
        with self.assertRaises(ValueError):
            publisher.validate_cookie('web_session=only')
        with self.assertRaises(ValueError):
            publisher.validate_cookie('a1=only')
        cookies = publisher.validate_cookie(COOKIE)
        self.assertEqual(cookies['a1'], 'test-a1')

    def test_desc_limit_counts_topic_markup(self):
        with self.assertRaises(ValueError) as error:
            publisher.validate_note(TITLE, '字' * 1000, self.images, ['话题'])
        self.assertIn('1000', str(error.exception))


class PublishUiTests(unittest.TestCase):
    """Real Playwright flow against the local fixture page."""

    @classmethod
    def setUpClass(cls):
        cls.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f'http://127.0.0.1:{cls.httpd.server_address[1]}'

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-rednote-ui-')
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name).resolve()
        shutil.copy2(ROOT / 'preferences.py', self.project / 'preferences.py')
        (self.project / '.env').write_text(f'XhsCreatorCookie="{COOKIE}"\n', encoding='utf-8')
        self.article = self.project / 'article'
        self.article.mkdir()
        from PIL import Image
        for name in ('xhs-01-cover.png', 'xhs-02-page.png'):
            Image.new('RGB', (1080, 1440), 'indigo').save(self.article / name)
        self.images = [str(self.article / 'xhs-01-cover.png'), str(self.article / 'xhs-02-page.png')]

    def publish(self, public=False, query='', timeout=30):
        instance = publisher.RednotePublisher(
            root=self.project, base_url=self.base_url, timeout=timeout,
            artifact_dir=self.article,
            publish_url=f'{self.base_url}/publish/publish{query}')
        return instance.publish(TITLE, '改了三个设置后稳定多了。', self.images,
                                ['AI工具', '效率'], public=public)

    def test_ui_publish_defaults_to_private_and_selects_topics(self):
        result = self.publish()
        self.assertEqual(result['status'], 'published')
        self.assertEqual(result['visibility'], 'private')
        self.assertEqual(result['note_id'], 'mocknote123')
        self.assertEqual(result['url'], 'https://www.xiaohongshu.com/explore/mocknote123')

    def test_ui_public_flag_is_honored(self):
        result = self.publish(public=True)
        self.assertEqual(result['visibility'], 'public')

    def test_ui_login_expired_is_reported_with_screenshot(self):
        with self.assertRaises(ValueError) as error:
            self.publish(query='?login=1')
        self.assertIn('Cookie', str(error.exception))
        self.assertTrue((self.article / 'publish-failure.png').is_file())

    def test_ui_failure_never_claims_success(self):
        with self.assertRaises(ValueError) as error:
            self.publish(query='?fail=1', timeout=3)
        self.assertIn('未观察到发布成功信号', str(error.exception))
        self.assertTrue((self.article / 'publish-failure.png').is_file())


class PublishCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-rednote-cli-')
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name).resolve()
        for name in ('openwrite.py', 'workflow.py', 'preferences.py', 'platforms.py'):
            shutil.copy2(ROOT / name, self.project / name)
        shutil.copytree(ROOT / 'skills', self.project / 'skills')
        (self.project / '.env').write_text(
            'WeChat=true\nWriterRole=SelfMediaBlogger\n', encoding='utf-8')
        self.article = self.project / 'articles/note'
        self.article.mkdir(parents=True)
        finish(self.article)
        workflow.complete_format(self.article, 'indigo', False,
                                 workflow.check_publishable(self.article, workflow.load(self.article)))

    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(self.project / 'openwrite.py'),
                               'publish', str(self.article), *args],
                              cwd=self.project, capture_output=True, text=True)

    def test_cli_dry_run_reports_private_without_cookie(self):
        result = self.run_cli('--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('发布预演', result.stdout)
        self.assertIn('仅自己可见', result.stdout)

    def test_cli_publish_requires_cookie(self):
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('XhsCreatorCookie', result.stderr)

    def test_cli_wechat_only_flags_are_rejected_for_wechat(self):
        args = Namespace(article=str(self.article), title=None, author=None, digest=None,
                         public=True, dry_run=False, headed=False)
        state = workflow.load(self.article)
        state['platform'] = 'wechat'  # 仅用于验证参数守卫，不实际发布
        with patch.object(cli.workflow, 'require_publishable', return_value={'title': TITLE}), \
             patch.object(cli.platforms, 'require_publish_adapter',
                          return_value={'rendered_artifact': 'article.html',
                                        'cover': {'output': 'cover.png'},
                                        'publisher': 'wechat-draft-publisher',
                                        'publisher_entry': 'publisher.py'}):
            with self.assertRaises(ValueError) as error:
                cli.publish_article(args)
        self.assertIn('仅支持小红书', str(error.exception))

    def test_publish_dispatches_ordered_card_set(self):
        args = Namespace(article=str(self.article), title=None, author=None, digest=None,
                         public=False, dry_run=False, headed=False)
        with patch.object(cli, 'run_skill', return_value=0) as execute:
            self.assertEqual(cli.publish_article(args), 0)
        name, entry, *arguments = execute.call_args.args
        self.assertEqual((name, entry), ('rednote-publisher', 'publish_note.py'))
        images = arguments[arguments.index('--images') + 1:arguments.index('--project-root')]
        self.assertEqual(images, [str(self.article / 'xhs-01-cover.png'),
                                  str(self.article / 'xhs-02-page.png')])
        self.assertNotIn('--public', arguments)
        self.assertIn('--desc', arguments)
        self.assertIn('--topics', arguments)


class PublishLimitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-rednote-limits-')
        self.addCleanup(self.tmp.cleanup)
        self.article = Path(self.tmp.name).resolve()

    def test_content_cards_cannot_exceed_platform_total(self):
        finish(self.article)
        plan(self.article, pages=18)
        with self.assertRaises(ValueError) as error:
            workflow.requests(self.article)
        self.assertIn('最多 17 张', str(error.exception))

    def test_long_desc_fails_publishability(self):
        finish(self.article)
        (self.article / 'note.md').write_text(f'# {TITLE}\n\n' + '字' * 1001 + '\n', encoding='utf-8')
        with self.assertRaises(ValueError) as error:
            workflow.check_publishable(self.article, workflow.load(self.article))
        self.assertIn('正文超过 1000 字', str(error.exception))


if __name__ == '__main__':
    unittest.main()
