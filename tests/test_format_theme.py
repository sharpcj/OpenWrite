"""Account format_theme config: task snapshots, format resolution and write-back."""
import layout
from argparse import Namespace
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import preferences
import workflow
from workflow_fixtures import finish_article

os.environ['OPENWRITE_BOARD_AUTO'] = '0'  # 测试不得拉起真实看板或弹浏览器

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('openwrite_format_theme_test', ROOT / 'openwrite.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)

CONFIG = ('wechat:\n  accounts:\n    主号:\n      format_theme: grace\n')


class FormatThemeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-format-theme-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.article = self.root / 'article'
        self.config = self.root / preferences.CONFIG_NAME
        self.config.write_text(CONFIG, encoding='utf-8')

    def cli(self, *args):
        for name in ('openwrite.py', 'workflow.py', 'preferences.py', 'platforms.py', 'layout.py'):
            shutil.copy2(ROOT / name, self.root / name)
        return subprocess.run([sys.executable, '-B', str(self.root / 'openwrite.py'), *args],
                              cwd=self.root, capture_output=True, text=True)

    def test_account_format_theme_is_validated(self):
        self.assertEqual(preferences.read_config(self.root)['wechat']['accounts']['主号']['format_theme'],
                         'grace')
        for bad in ('', 'grace\nmodern', '   '):
            with self.subTest(bad=bad):
                # JSON 字符串即合法 YAML 双引号标量，换行以 \n 转义写入。
                self.config.write_text('wechat:\n  accounts:\n    主号:\n'
                                       f'      format_theme: {json.dumps(bad)}\n', encoding='utf-8')
                with self.assertRaises(ValueError):
                    preferences.read_config(self.root)

    def test_resolution_explicit_wins_and_unset_is_empty(self):
        self.assertEqual(preferences.format_theme(self.root, account='主号'), 'grace')
        self.assertEqual(preferences.format_theme(self.root, account='主号', theme='modern'), 'modern')
        self.config.write_text('wechat:\n  accounts:\n    主号: {}\n', encoding='utf-8')
        self.assertEqual(preferences.format_theme(self.root, account='主号'), '')
        self.assertEqual(preferences.format_theme(self.root, account='主号', theme='simple'), 'simple')

    def test_new_persists_snapshot_and_explicit_flag_wins(self):
        result = self.cli('new', 'configured')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(workflow.load(self.root / 'articles/configured')['format_theme'], 'grace')
        self.assertIn('排版主题：grace', result.stdout)
        result = self.cli('new', 'explicit', '--format-theme', 'modern')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(workflow.load(self.root / 'articles/explicit')['format_theme'], 'modern')

    def test_new_without_config_has_no_snapshot(self):
        self.config.write_text('wechat:\n  accounts:\n    主号: {}\n', encoding='utf-8')
        result = self.cli('new', 'plain')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('format_theme', workflow.load(self.root / 'articles/plain'))

    def test_format_theme_is_wechat_only(self):
        result = self.cli('new', 'rednote', '--platform', 'rednote', '--format-theme', 'grace')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'articles/rednote').exists())
        state = workflow.initialize(self.root / 'direct', '测试', platform='rednote', format_theme='grace')
        self.assertNotIn('format_theme', state)

    def test_workflow_init_persists_snapshot(self):
        existing = self.root / 'existing'
        existing.mkdir()
        result = self.cli('workflow', 'init', str(existing), '--format-theme', 'simple')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(workflow.load(existing)['format_theme'], 'simple')

    def test_status_and_preferences_show_format_theme(self):
        result = self.cli('new', 'topic')
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.cli('workflow', 'status', str(self.root / 'articles/topic'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('排版主题：grace', result.stdout)
        result = self.cli('preferences', '--platform', 'wechat')
        self.assertEqual(result.returncode, 0, result.stderr)
        selection = json.loads(result.stdout[:result.stdout.index('OutlineApproval')])
        self.assertEqual(selection['format_theme'], 'grace')

    def test_format_uses_snapshot_and_override_writes_back(self):
        workflow.initialize(self.article, '测试文章', format_theme='grace')
        finish_article(self.article, text='# 测试文章\n\n# 正文章节\n\n正文内容。\n\n> 推荐做法。\n')
        with patch.object(workflow.preferences, 'credential_value', return_value=''):
            self.assertEqual(cli.format_article(Namespace(
                article=str(self.article), theme=None, no_preformat=True)), 0)
            self.assertEqual(workflow.require_publishable(self.article)['theme'], 'grace')
            self.assertIn('#DEC6FB', (self.article / 'article.html').read_text(encoding='utf-8'))
            # 显式覆盖：当次生效并回写快照。
            self.assertEqual(cli.format_article(Namespace(
                article=str(self.article), theme='modern', no_preformat=True)), 0)
            self.assertEqual(workflow.load(self.article)['format_theme'], 'modern')
            self.assertEqual(workflow.require_publishable(self.article)['theme'], 'modern')
            # 缺省重跑沿用回写后的快照，不回到账号配置。
            self.config.write_text('wechat:\n  accounts:\n    主号:\n      format_theme: simple\n',
                                   encoding='utf-8')
            self.assertEqual(cli.format_article(Namespace(
                article=str(self.article), theme=None, no_preformat=True)), 0)
            self.assertEqual(workflow.require_publishable(self.article)['theme'], 'modern')

    def test_old_task_without_snapshot_uses_default(self):
        finish_article(self.article)
        with patch.object(workflow.preferences, 'credential_value', return_value=''):
            self.assertEqual(cli.format_article(Namespace(
                article=str(self.article), theme=None, no_preformat=True)), 0)
        self.assertEqual(workflow.require_publishable(self.article)['theme'], 'default')
        self.assertEqual(workflow.load(self.article)['format_theme'], 'default')

    def test_failed_format_preserves_snapshot_and_artifact(self):
        workflow.initialize(self.article, '测试文章', format_theme='grace')
        finish_article(self.article)
        with patch.object(workflow.preferences, 'credential_value', return_value=''):
            self.assertEqual(cli.format_article(Namespace(
                article=str(self.article), theme=None, no_preformat=True)), 0)
        output = self.article / 'article.html'
        before = output.read_bytes()
        state_before = workflow.load(self.article)
        # 空转换使可发布性检查失败：快照与产物都不变。
        with patch.object(cli, 'run_skill', return_value=0):
            with self.assertRaises(ValueError):
                cli.format_article(Namespace(article=str(self.article), theme='modern', no_preformat=True))
        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(workflow.load(self.article), state_before)

    def test_load_rejects_malformed_snapshot_theme(self):
        workflow.initialize(self.article, '测试文章', format_theme='grace')
        state = workflow.load(self.article)
        for bad in ('', 'grace\nmodern', 3):
            with self.subTest(bad=bad):
                workflow.write_json(layout.path(self.article, 'workflow.json'),
                                    dict(state, format_theme=bad))
                with self.assertRaises(ValueError):
                    workflow.load(self.article)


if __name__ == '__main__':
    unittest.main()