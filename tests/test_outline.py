"""Title/outline checkpoint between analysis and draft, including the config opt-out."""
import layout
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import preferences
import workflow
from workflow_fixtures import approve_outline, seed_body
import os
os.environ['OPENWRITE_BOARD_AUTO'] = '0'  # 测试不得拉起真实看板或弹浏览器

ROOT = Path(__file__).resolve().parents[1]


def reach_analysis(article):
    workflow.initialize(article, '测试文章')
    workflow.write_json(layout.path(article, 'sources.json'), {'version': 1, 'sources': [
        {'id': 's1', 'title': '用户资料', 'kind': 'user', 'content': '可验证的测试资料内容'},
    ]})
    workflow.complete(article, 'search')
    (layout.path(article, 'analysis.md')).write_text('# 分析\n\nsource:s1 支持文章中的观点。\n', encoding='utf-8')
    workflow.complete(article, 'analysis')


class OutlineCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-outline-')
        self.addCleanup(self.tmp.cleanup)
        self.article = Path(self.tmp.name).resolve()
        reach_analysis(self.article)

    def write_draft(self, title='测试文章'):
        (layout.path(self.article, 'draft.md')).write_text(f'# {title}\n\n正文内容。\n', encoding='utf-8')

    def test_draft_is_blocked_until_user_approves_title_and_outline(self):
        self.write_draft()
        with self.assertRaises(ValueError):
            workflow.complete(self.article, 'draft')
        approve_outline(self.article)
        data = workflow.read_json(layout.path(self.article, 'outline.json'))
        data['approved'] = False
        workflow.write_json(layout.path(self.article, 'outline.json'), data)
        with self.assertRaises(ValueError) as error:
            workflow.complete(self.article, 'draft')
        self.assertIn('尚未获得用户确认', str(error.exception))
        data['approved'] = True
        workflow.write_json(layout.path(self.article, 'outline.json'), data)
        workflow.complete(self.article, 'draft')
        self.assertEqual(workflow.current(workflow.load(self.article)), 'cover')

    def test_candidates_need_three_titles_and_both_mandatory_styles(self):
        self.write_draft()
        approve_outline(self.article)
        data = workflow.read_json(layout.path(self.article, 'outline.json'))
        data['candidates'] = data['candidates'][:2]
        workflow.write_json(layout.path(self.article, 'outline.json'), data)
        with self.assertRaises(ValueError):
            workflow.complete(self.article, 'draft')
        approve_outline(self.article)
        data = workflow.read_json(layout.path(self.article, 'outline.json'))
        data['candidates'][0]['style'] = '利益实用'
        workflow.write_json(layout.path(self.article, 'outline.json'), data)
        with self.assertRaises(ValueError) as error:
            workflow.complete(self.article, 'draft')
        self.assertIn('激进悬念', str(error.exception))

    def test_user_defined_title_is_allowed_and_recorded(self):
        self.write_draft('用户自己写的标题')
        approve_outline(self.article, title='用户自己写的标题', source='user')
        workflow.complete(self.article, 'draft')
        self.assertEqual(workflow.load(self.article)['title'], '用户自己写的标题')
        # A candidate-source choice must exist among the candidates.
        workflow.reset(self.article, 'draft')
        approve_outline(self.article, title='不在候选里的标题', source='candidate')
        with self.assertRaises(ValueError):
            workflow.complete(self.article, 'draft')

    def test_changing_outline_after_approval_invalidates_it(self):
        self.write_draft()
        approve_outline(self.article)
        (layout.path(self.article, 'outline.md')).write_text('# 改了大纲\n\n用户还没重新确认。\n', encoding='utf-8')
        with self.assertRaises(ValueError) as error:
            workflow.complete(self.article, 'draft')
        self.assertIn('重新取得用户确认', str(error.exception))
        approve_outline(self.article)
        workflow.complete(self.article, 'draft')

    def test_draft_heading_must_match_the_approved_title(self):
        self.write_draft('偷偷换掉的标题')
        approve_outline(self.article)
        with self.assertRaises(ValueError) as error:
            workflow.complete(self.article, 'draft')
        self.assertIn('标题必须与用户确认的标题一致', str(error.exception))

    def test_approved_outline_change_expires_completed_draft(self):
        article = self.article / 'fresh'
        article.mkdir()
        seed_body(article)
        self.assertIsNone(workflow.stale_step(article, workflow.load(article)))
        (layout.path(article, 'outline.md')).write_text('# 新大纲\n\n确认后又被修改。\n', encoding='utf-8')
        self.assertEqual(workflow.stale_step(article, workflow.load(article))[0], 'draft')

    def test_legacy_task_without_field_keeps_original_behaviour(self):
        path = layout.path(self.article, 'workflow.json')
        state = json.loads(path.read_text())
        del state['outline_approval']
        path.write_text(json.dumps(state))
        self.write_draft()
        workflow.complete(self.article, 'draft')


class OutlineConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-outline-config-')
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name).resolve()
        for name in ('openwrite.py', 'workflow.py', 'preferences.py', 'platforms.py', 'layout.py'):
            shutil.copy2(ROOT / name, self.project / name)
        shutil.copytree(ROOT / 'skills', self.project / 'skills')

    def write_env(self, text):
        (self.project / '.env').write_text(text, encoding='utf-8')

    def run_cli(self, *args, ok=True):
        result = subprocess.run([sys.executable, '-B', str(self.project / 'openwrite.py'), *args],
                                cwd=self.project, capture_output=True, text=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def test_flag_defaults_to_true_and_rejects_invalid_values(self):
        self.write_env('WeChat=true\nWriterRole=SelfMediaBlogger\n')
        self.assertTrue(preferences.outline_approval(self.project))
        self.write_env('WeChat=true\nWriterRole=SelfMediaBlogger\nOutlineApproval=false\n')
        self.assertFalse(preferences.outline_approval(self.project))
        self.write_env('OutlineApproval=maybe\n')
        with self.assertRaises(ValueError):
            preferences.outline_approval(self.project)

    def test_config_opt_out_is_persisted_and_lets_draft_skip_outline(self):
        self.write_env('WeChat=true\nWriterRole=SelfMediaBlogger\nOutlineApproval=false\n')
        self.run_cli('new', 'auto', '--title', '自动写作')
        article = self.project / 'articles/auto'
        state = json.loads((layout.path(article, 'workflow.json')).read_text())
        self.assertFalse(state['outline_approval'])
        self.assertIn('用户已授权跳过', (layout.path(article, 'brief.md')).read_text())
        workflow.write_json(layout.path(article, 'sources.json'), {'version': 1, 'sources': [
            {'id': 's1', 'title': '用户资料', 'kind': 'user', 'content': '实际资料'},
        ]})
        self.run_cli('workflow', 'complete', str(article), '--step', 'search')
        (layout.path(article, 'analysis.md')).write_text('source:s1 支持观点。')
        self.run_cli('workflow', 'complete', str(article), '--step', 'analysis')
        (layout.path(article, 'draft.md')).write_text('# 自动写作\n\n正文内容。\n')
        self.run_cli('workflow', 'complete', str(article), '--step', 'draft')
        self.assertFalse((layout.path(article, 'outline.json')).exists())
        # Changing the config later must not alter the saved task choice.
        self.write_env('WeChat=true\nWriterRole=SelfMediaBlogger\nOutlineApproval=true\n')
        status = self.run_cli('workflow', 'status', str(article))
        self.assertIn('标题与大纲检查点：已授权跳过', status.stdout)

    def test_explicit_skip_flag_overrides_enabled_config(self):
        self.write_env('WeChat=true\nWriterRole=SelfMediaBlogger\nOutlineApproval=true\n')
        self.run_cli('new', 'manual', '--title', '手动确认')
        self.assertTrue(json.loads(layout.path(self.project / 'articles/manual', 'workflow.json').read_text())['outline_approval'])
        self.run_cli('new', 'skipped', '--title', '跳过确认', '--skip-outline')
        self.assertFalse(json.loads(layout.path(self.project / 'articles/skipped', 'workflow.json').read_text())['outline_approval'])
        manual = self.project / 'articles/manual'
        workflow.write_json(layout.path(manual, 'sources.json'), {'version': 1, 'sources': [
            {'id': 's1', 'title': '用户资料', 'kind': 'user', 'content': '实际资料'},
        ]})
        workflow.complete(manual, 'search')
        (layout.path(manual, 'analysis.md')).write_text('source:s1 支持观点。')
        workflow.complete(manual, 'analysis')
        status = self.run_cli('workflow', 'status', str(manual))
        self.assertIn('标题与大纲检查点：开启', status.stdout)
        self.assertIn('outline.md', status.stdout)


if __name__ == '__main__':
    unittest.main()
