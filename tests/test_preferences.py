"""Defaults, explicit task choices, ambiguity, and persistence without global state."""
import layout
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import preferences
import os
os.environ['OPENWRITE_BOARD_AUTO'] = '0'  # 测试不得拉起真实看板或弹浏览器

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = ('defaults:\n  writer_role: blogger\n'
            'wechat:\n  accounts:\n    主号: {}\n')
WECHAT_ONLY = 'wechat:\n  accounts:\n    主号: {}\n'
BOTH = ('wechat:\n  accounts:\n    主号: {}\n'
        'rednote:\n  accounts:\n    主账号:\n      cookie: "a1=x; web_session=y"\n')


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-preferences-')
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name).resolve()
        self.config = self.project / preferences.CONFIG_NAME
        self.config.write_text(DEFAULTS, encoding='utf-8')

    def flags(self, text):
        self.config.write_text(text, encoding='utf-8')

    def run_cli(self, *args):
        for name in ('openwrite.py', 'workflow.py', 'preferences.py', 'platforms.py', 'layout.py'):
            shutil.copy2(ROOT / name, self.project / name)
        return subprocess.run([sys.executable, '-B', str(self.project / 'openwrite.py'), *args],
                              cwd=self.project, capture_output=True, text=True)

    def test_unique_defaults_and_blogger_default(self):
        selection = preferences.resolve(self.project)
        self.assertEqual(selection, {'platform': 'wechat', 'account': '主号', 'perspective': 'blogger',
                                     'selection_source': {'platform': 'config', 'account': 'config',
                                                          'perspective': 'config'}})

    def test_explicit_task_choices_override_both_defaults_without_writing_config(self):
        before = self.config.read_bytes()
        selection = preferences.resolve(self.project, 'rednote', 'product')
        self.assertEqual((selection['platform'], selection['perspective']), ('rednote', 'product'))
        self.assertEqual(selection['selection_source'], {'platform': 'explicit', 'perspective': 'explicit'})
        self.assertEqual(self.config.read_bytes(), before)

    def test_platform_and_perspective_are_resolved_independently(self):
        selection = preferences.resolve(self.project, perspective='tech')
        self.assertEqual((selection['platform'], selection['perspective']), ('wechat', 'tech'))
        selection = preferences.resolve(self.project, platform='rednote')
        self.assertEqual((selection['platform'], selection['perspective']), ('rednote', 'blogger'))

    def test_zero_or_multiple_enabled_platforms_require_confirmation(self):
        for text in ('wechat:\n  enabled: false\n  accounts:\n    主号: {}\n', BOTH, ''):
            with self.subTest(text=text):
                self.flags(text)
                with self.assertRaises(preferences.ChoiceRequired) as error:
                    preferences.resolve(self.project)
                self.assertIn('--platform', str(error.exception))
                self.assertEqual(preferences.resolve(self.project, platform='wechat')['platform'], 'wechat')

    def test_writer_role_single_value_and_builtin_default(self):
        for role, expected in (('blogger', 'blogger'), ('tech', 'tech'), ('product', 'product'),
                               ('SelfMediaBlogger', 'blogger'), ('TechWriter', 'tech'),
                               ('ProductManager', 'product'), ('techwriter', 'tech')):
            with self.subTest(role=role):
                self.flags(f'defaults:\n  writer_role: {role}\n' + WECHAT_ONLY)
                selection = preferences.resolve(self.project)
                self.assertEqual(selection['perspective'], expected)
                self.assertEqual(selection['selection_source']['perspective'], 'config')
        for text in (WECHAT_ONLY, 'defaults:\n  writer_role: ""\n' + WECHAT_ONLY):
            with self.subTest(text=text):
                self.flags(text)
                selection = preferences.resolve(self.project)
                self.assertEqual(selection['perspective'], 'blogger')
                self.assertEqual(selection['selection_source']['perspective'], 'default')

    def test_invalid_writer_role_or_legacy_switches_are_reported(self):
        self.flags('defaults:\n  writer_role: engineer\n' + WECHAT_ONLY)
        with self.assertRaises(ValueError) as error:
            preferences.resolve(self.project)
        self.assertIn('writer_role', str(error.exception))
        # 旧版布尔视角开关如今是未知顶层节，同样被拒绝。
        for text in ('SelfMediaBlogger: true\n' + WECHAT_ONLY,
                     'defaults:\n  writer_role: tech\nProductManager: false\n' + WECHAT_ONLY):
            with self.subTest(text=text):
                self.flags(text)
                with self.assertRaises(ValueError):
                    preferences.resolve(self.project)

    def test_ambiguous_platform_needs_choice_while_role_keeps_configured(self):
        self.flags('defaults:\n  writer_role: product\n' + BOTH)
        with self.assertRaises(preferences.ChoiceRequired) as error:
            preferences.resolve(self.project)
        self.assertIn('--platform', str(error.exception))
        self.assertNotIn('--perspective', str(error.exception))
        selection = preferences.resolve(self.project, platform='rednote')
        self.assertEqual((selection['platform'], selection['perspective']), ('rednote', 'product'))

    def test_missing_config_needs_platform_confirmation_but_role_defaults(self):
        self.config.unlink()
        with self.assertRaises(preferences.ChoiceRequired):
            preferences.resolve(self.project)
        selection = preferences.resolve(self.project, platform='wechat')
        self.assertEqual(selection['perspective'], 'blogger')
        self.assertEqual(selection['selection_source']['perspective'], 'default')
        self.assertEqual(preferences.resolve(self.project, 'wechat', 'blogger')['platform'], 'wechat')

    def test_yaml_comments_and_strings_are_never_executed(self):
        marker = self.project / 'must-not-exist'
        self.flags('# 注释\ndefaults:\n  writer_role: tech\n'
                   f'wechat:\n  accounts:\n    主号:\n      author: "$(touch {marker})"\n')
        selection = preferences.resolve(self.project)
        self.assertEqual((selection['platform'], selection['perspective']), ('wechat', 'tech'))
        self.assertFalse(marker.exists())

    def test_invalid_boolean_or_unknown_field_is_reported(self):
        for text in ('defaults:\n  outline_approval: maybe\n' + WECHAT_ONLY,
                     'wechat:\n  accounts:\n    主号:\n      bogus: 1\n',
                     'defaults:\n  outline_approval: 1\n' + WECHAT_ONLY):
            self.flags(text)
            with self.assertRaises(ValueError):
                preferences.resolve(self.project)

    def test_cli_ambiguity_creates_no_task_until_user_choice_is_supplied(self):
        self.flags(BOTH)
        result = self.run_cli('new', 'topic')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('用户明确确认', result.stderr)
        self.assertFalse((self.project / 'articles/topic').exists())
        result = self.run_cli('new', 'topic', '--platform', 'wechat')
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads(layout.path(self.project / 'articles/topic', 'workflow.json').read_text())
        self.assertEqual((state['platform'], state['perspective'], state['account']),
                         ('wechat', 'blogger', '主号'))

    def test_new_task_persists_choices_and_resume_does_not_read_changed_defaults(self):
        result = self.run_cli('new', 'topic', '--perspective', 'product')
        self.assertEqual(result.returncode, 0, result.stderr)
        article = self.project / 'articles/topic'
        path = layout.path(article, 'workflow.json')
        before = path.read_bytes()
        state = json.loads(before)
        self.assertEqual(state['selection_source'],
                         {'platform': 'config', 'account': 'config', 'perspective': 'explicit'})
        self.flags('rednote:\n  accounts:\n    主账号:\n      cookie: "a1=x; web_session=y"\n')
        result = self.run_cli('workflow', 'status', str(article))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('任务平台：微信；写作视角：产品经理', result.stdout)
        self.assertEqual(path.read_bytes(), before)

    def test_legacy_type_alias_is_explicit_and_workflow_init_uses_defaults(self):
        result = self.run_cli('new', 'legacy', '--type', 'tech')
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads(layout.path(self.project / 'articles/legacy', 'workflow.json').read_text())
        self.assertEqual(state['perspective'], 'tech')
        existing = self.project / 'existing'
        existing.mkdir()
        result = self.run_cli('workflow', 'init', str(existing))
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads((layout.path(existing, 'workflow.json')).read_text())
        self.assertEqual((state['platform'], state['perspective']), ('wechat', 'blogger'))

    def test_legacy_tasks_keep_wechat_and_their_original_view(self):
        existing = self.project / 'old'
        existing.mkdir()
        path = layout.path(existing, 'workflow.json')
        path.write_text(json.dumps({'version': 1, 'title': '旧任务', 'type': 'product',
                                    'revision': 0, 'completed': []}))
        before = path.read_bytes()
        self.flags('rednote:\n  accounts:\n    主账号:\n      cookie: "a1=x; web_session=y"\n')
        result = self.run_cli('workflow', 'status', str(existing))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('任务平台：微信；写作视角：产品经理', result.stdout)
        self.assertEqual(path.read_bytes(), before)

    def test_rednote_choice_is_saved_and_writing_pipeline_is_available(self):
        self.flags('rednote:\n  accounts:\n    主账号:\n      cookie: "a1=x; web_session=y"\n')
        result = self.run_cli('new', 'rednote-topic', '--platform', 'rednote')
        self.assertEqual(result.returncode, 0, result.stderr)
        article = self.project / 'articles/rednote-topic'
        state = json.loads((layout.path(article, 'workflow.json')).read_text())
        self.assertEqual(state['platform'], 'rednote')
        self.assertEqual(state['account'], '主账号')
        (layout.path(article, 'sources.json')).write_text(json.dumps({'version': 1, 'sources': [
            {'id': 's1', 'title': '用户资料', 'kind': 'user', 'content': '实际资料内容'},
        ]}, ensure_ascii=False), encoding='utf-8')
        result = self.run_cli('workflow', 'complete', str(article), '--step', 'search')
        self.assertEqual(result.returncode, 0, result.stderr)
        status = self.run_cli('workflow', 'status', str(article))
        self.assertIn('任务平台：小红书', status.stdout)
        self.assertIn('rednote-note-writer', status.stdout)
        self.assertIn('生成可发布交付件', status.stdout)


if __name__ == '__main__':
    unittest.main()
