"""Defaults, explicit task choices, ambiguity, and persistence without global state."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import preferences

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = 'WeChat=true\nRednote=false\nSelfMediaBlogger=true\nTechWriter=false\nProductManager=false\n'


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-preferences-')
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name).resolve()
        self.config = self.project / '.env'
        self.config.write_text(DEFAULTS)

    def flags(self, text):
        self.config.write_text(text, encoding='utf-8')

    def run_cli(self, *args):
        for name in ('openwrite.py', 'workflow.py', 'preferences.py', 'platforms.py'):
            shutil.copy2(ROOT / name, self.project / name)
        return subprocess.run([sys.executable, '-B', str(self.project / 'openwrite.py'), *args],
                              cwd=self.project, capture_output=True, text=True)

    def test_unique_defaults_and_blogger_default(self):
        selection = preferences.resolve(self.project)
        self.assertEqual(selection, {'platform': 'wechat', 'perspective': 'blogger',
                                     'selection_source': {'platform': 'config', 'perspective': 'config'}})

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
        for flags in ('WeChat=false\nRednote=false', 'WeChat=true\nRednote=true', ''):
            with self.subTest(flags=flags):
                self.flags(flags+'\nSelfMediaBlogger=true\n')
                with self.assertRaises(preferences.ChoiceRequired) as error:
                    preferences.resolve(self.project)
                self.assertIn('--platform', str(error.exception))
                self.assertEqual(preferences.resolve(self.project, platform='wechat')['platform'], 'wechat')

    def test_zero_or_multiple_enabled_perspectives_require_confirmation(self):
        for flags in ('SelfMediaBlogger=false\nTechWriter=false\nProductManager=false',
                      'SelfMediaBlogger=true\nTechWriter=true',
                      'TechWriter=true\nProductManager=true', ''):
            with self.subTest(flags=flags):
                self.flags('WeChat=true\n'+flags+'\n')
                with self.assertRaises(preferences.ChoiceRequired) as error:
                    preferences.resolve(self.project)
                self.assertIn('--perspective', str(error.exception))
                self.assertEqual(preferences.resolve(self.project, perspective='product')['perspective'], 'product')

    def test_both_ambiguous_groups_need_explicit_choices(self):
        self.flags('WeChat=true\nRednote=true\nSelfMediaBlogger=true\nProductManager=true\n')
        with self.assertRaises(preferences.ChoiceRequired) as error:
            preferences.resolve(self.project)
        self.assertIn('--platform', str(error.exception))
        self.assertIn('--perspective', str(error.exception))
        with self.assertRaises(preferences.ChoiceRequired):
            preferences.resolve(self.project, platform='wechat')
        self.assertEqual(preferences.resolve(self.project, 'rednote', 'tech')['perspective'], 'tech')

    def test_missing_config_needs_confirmation_unless_both_choices_are_explicit(self):
        self.config.unlink()
        with self.assertRaises(preferences.ChoiceRequired):
            preferences.resolve(self.project)
        self.assertEqual(preferences.resolve(self.project, 'wechat', 'blogger')['platform'], 'wechat')

    def test_parser_handles_quotes_comments_and_never_executes_file(self):
        marker = self.project / 'must-not-exist'
        self.flags(f'export WeChat="TRUE" # comment\nRednote=FALSE\nSelfMediaBlogger=\'true\'\n'
                   f'UNRELATED=$(touch {marker})\n')
        self.assertEqual(preferences.resolve(self.project)['platform'], 'wechat')
        self.assertFalse(marker.exists())

    def test_invalid_boolean_or_duplicate_key_is_reported(self):
        for flags in ('WeChat=yes\nSelfMediaBlogger=true\n',
                      'WeChat=true\nWeChat=false\nSelfMediaBlogger=true\n'):
            self.flags(flags)
            with self.assertRaises(ValueError):
                preferences.resolve(self.project)

    def test_cli_ambiguity_creates_no_task_until_user_choice_is_supplied(self):
        self.flags('WeChat=true\nRednote=true\nSelfMediaBlogger=true\n')
        result = self.run_cli('new', 'topic')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('用户明确确认', result.stderr)
        self.assertFalse((self.project / 'articles/topic').exists())
        result = self.run_cli('new', 'topic', '--platform', 'wechat')
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads((self.project / 'articles/topic/workflow.json').read_text())
        self.assertEqual((state['platform'], state['perspective']), ('wechat', 'blogger'))

    def test_new_task_persists_choices_and_resume_does_not_read_changed_defaults(self):
        result = self.run_cli('new', 'topic', '--perspective', 'product')
        self.assertEqual(result.returncode, 0, result.stderr)
        path = self.project / 'articles/topic/workflow.json'
        before = path.read_bytes()
        state = json.loads(before)
        self.assertEqual(state['selection_source'], {'platform': 'config', 'perspective': 'explicit'})
        self.flags('WeChat=false\nRednote=true\nSelfMediaBlogger=true\n')
        result = self.run_cli('workflow', 'status', str(path.parent))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('任务平台：微信；写作视角：产品经理', result.stdout)
        self.assertEqual(path.read_bytes(), before)

    def test_legacy_type_alias_is_explicit_and_workflow_init_uses_defaults(self):
        result = self.run_cli('new', 'legacy', '--type', 'tech')
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads((self.project / 'articles/legacy/workflow.json').read_text())
        self.assertEqual(state['perspective'], 'tech')
        existing = self.project / 'existing'
        existing.mkdir()
        result = self.run_cli('workflow', 'init', str(existing))
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads((existing / 'workflow.json').read_text())
        self.assertEqual((state['platform'], state['perspective']), ('wechat', 'blogger'))

    def test_legacy_tasks_keep_wechat_and_their_original_view(self):
        existing = self.project / 'old'
        existing.mkdir()
        path = existing / 'workflow.json'
        path.write_text(json.dumps({'version': 1, 'title': '旧任务', 'type': 'product',
                                    'revision': 0, 'completed': []}))
        before = path.read_bytes()
        self.flags('Rednote=true\nSelfMediaBlogger=true\n')
        result = self.run_cli('workflow', 'status', str(existing))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('任务平台：微信；写作视角：产品经理', result.stdout)
        self.assertEqual(path.read_bytes(), before)

    def test_rednote_choice_is_saved_and_writing_pipeline_is_available(self):
        result = self.run_cli('new', 'rednote-topic', '--platform', 'rednote')
        self.assertEqual(result.returncode, 0, result.stderr)
        article = self.project / 'articles/rednote-topic'
        state = json.loads((article / 'workflow.json').read_text())
        self.assertEqual(state['platform'], 'rednote')
        (article / 'sources.json').write_text(json.dumps({'version': 1, 'sources': [
            {'id': 's1', 'title': '用户资料', 'kind': 'user', 'content': '实际资料内容'},
        ]}, ensure_ascii=False), encoding='utf-8')
        result = self.run_cli('workflow', 'complete', str(article), '--step', 'search')
        self.assertEqual(result.returncode, 0, result.stderr)
        status = self.run_cli('workflow', 'status', str(article))
        self.assertIn('任务平台：小红书', status.stdout)
        self.assertIn('rednote-note-writer', status.stdout)
        self.assertIn('组装并保存可发布产物', status.stdout)


if __name__ == '__main__':
    unittest.main()
