"""Writer role presets: discovery, resolution, snapshots and role-driven gates."""
import layout
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import preferences
import workflow
import writer_roles


ROOT = Path(__file__).resolve().parents[1]


class RolePresetTests(unittest.TestCase):
    def test_builtin_roles_are_discovered_with_labels(self):
        self.assertEqual(writer_roles.list_roles(),
                         ['blogger', 'news', 'novelist', 'product', 'tech'])
        labels = writer_roles.labels()
        self.assertEqual(labels['news'], '新闻记者')
        self.assertEqual(labels['novelist'], '小说家')
        self.assertEqual(preferences.PERSPECTIVE_LABELS, labels)

    def test_resolution_accepts_ids_names_aliases_case_insensitively(self):
        for value, expected in (('blogger', 'blogger'), ('SelfMediaBlogger', 'blogger'),
                                ('techwriter', 'tech'), ('技术作者', 'tech'),
                                ('ProductManager', 'product'), ('NewsReporter', 'news'),
                                ('新闻记者', 'news'), ('NOVELIST', 'novelist'), ('小说家', 'novelist')):
            with self.subTest(value=value):
                self.assertEqual(writer_roles.resolve_role(value), expected)
        with self.assertRaises(ValueError):
            writer_roles.resolve_role('engineer')

    def test_role_files_are_validated(self):
        with tempfile.TemporaryDirectory(prefix='openwrite-roles-') as tmp:
            roles = Path(tmp)
            with patch.object(writer_roles, 'ROLES_DIR', roles):
                (roles / 'bad.yaml').write_text('name: 坏角色\n', encoding='utf-8')
                with self.assertRaises(ValueError):
                    writer_roles.load_role('bad')
                (roles / 'bad.yaml').write_text(
                    'name: 坏角色\nconstraints: 约束\ngates:\n  sources_required: yes-please\n',
                    encoding='utf-8')
                with self.assertRaises(ValueError):
                    writer_roles.load_role('bad')
                (roles / 'bad.yaml').write_text(
                    'name: 坏角色\nconstraints: 约束\ngates:\n  unknown_gate: true\n',
                    encoding='utf-8')
                with self.assertRaises(ValueError):
                    writer_roles.load_role('bad')
                (roles / 'good.yaml').write_text(
                    'name: 好角色\nconstraints: 约束文本\nskills:\n  wechat: openwrite-generic-writer\n',
                    encoding='utf-8')
                data = writer_roles.load_role('good')
                # 未声明的门禁沿用缺省（现行通用规则）。
                self.assertEqual(data['gates'], writer_roles.GATE_DEFAULTS)

    def test_config_writer_role_accepts_new_roles(self):
        with tempfile.TemporaryDirectory(prefix='openwrite-role-config-') as tmp:
            project = Path(tmp)
            for role, expected in (('news', 'news'), ('NewsReporter', 'news'),
                                   ('novelist', 'novelist'), ('Novelist', 'novelist')):
                with self.subTest(role=role):
                    (project / 'openwrite.yaml').write_text(
                        f'defaults:\n  writer_role: {role}\n'
                        'wechat:\n  accounts:\n    主号: {}\n', encoding='utf-8')
                    selection = preferences.resolve(project)
                    self.assertEqual(selection['perspective'], expected)


class RoleGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-role-gates-')
        self.addCleanup(self.tmp.cleanup)
        self.article = Path(self.tmp.name).resolve()

    def start(self, perspective):
        workflow.initialize(self.article, '测试文章', perspective)
        return workflow.load(self.article)

    def write_sources(self, items):
        workflow.write_json(layout.path(self.article, 'sources.json'),
                            {'version': 1, 'sources': items})

    def write_analysis(self, text):
        (layout.path(self.article, 'analysis.md')).write_text(text, encoding='utf-8')

    def test_initialize_snapshots_role_profile(self):
        state = self.start('novelist')
        profile = state['writer_profile']
        self.assertEqual(profile['role'], 'novelist')
        self.assertEqual(profile['name'], '小说家')
        self.assertIn('虚构', profile['constraints'])
        self.assertFalse(profile['gates']['sources_required'])
        self.assertFalse(profile['gates']['source_citations_required'])

    def test_novelist_allows_empty_sources_and_uncited_analysis(self):
        self.start('novelist')
        self.write_sources([])
        workflow.complete(self.article, 'search')
        self.write_analysis('# 分析\n\n创作构思与悬念设计。\n')
        workflow.complete(self.article, 'analysis')

    def test_novelist_still_rejects_unknown_source_references(self):
        self.start('novelist')
        self.write_sources([])
        workflow.complete(self.article, 'search')
        self.write_analysis('# 分析\n\nsource:ghost 不存在。\n')
        with self.assertRaises(ValueError):
            workflow.complete(self.article, 'analysis')

    def test_fact_roles_require_sources_and_citations(self):
        for perspective in ('blogger', 'tech', 'product', 'news'):
            with self.subTest(perspective=perspective):
                article = Path(self.tmp.name) / perspective
                article.mkdir()
                with patch.object(self, 'article', article):
                    self.start(perspective)
                    self.write_sources([])
                    with self.assertRaises(ValueError):
                        workflow.complete(self.article, 'search')
                    self.write_sources([{'id': 's1', 'title': '资料', 'kind': 'user', 'content': '实际内容'}])
                    workflow.complete(self.article, 'search')
                    self.write_analysis('# 分析\n\n无引用。\n')
                    with self.assertRaises(ValueError):
                        workflow.complete(self.article, 'analysis')
                    self.write_analysis('# 分析\n\nsource:s1 支持观点。\n')
                    workflow.complete(self.article, 'analysis')

    def test_snapshot_gates_survive_later_preset_edits(self):
        self.start('blogger')
        # 任务创建后把 blogger 预设改成允许空来源：已有任务仍按快照执行。
        with tempfile.TemporaryDirectory(prefix='openwrite-roles-edit-') as tmp:
            roles = Path(tmp)
            shutil.copytree(writer_roles.ROLES_DIR, roles, dirs_exist_ok=True)
            (roles / 'blogger.yaml').write_text(
                'name: 自媒体博主\nconstraints: 新约束\ngates:\n  sources_required: false\n',
                encoding='utf-8')
            with patch.object(writer_roles, 'ROLES_DIR', roles):
                self.write_sources([])
                with self.assertRaises(ValueError):
                    workflow.complete(self.article, 'search')

    def test_old_task_without_snapshot_falls_back_to_current_role(self):
        self.start('blogger')
        state = workflow.load(self.article)
        del state['writer_profile']
        workflow.write_json(layout.path(self.article, 'workflow.json'), state)
        self.write_sources([])
        with self.assertRaises(ValueError):
            workflow.complete(self.article, 'search')

    def test_load_rejects_malformed_profile(self):
        self.start('blogger')
        state = workflow.load(self.article)
        for bad in ({'role': 'blogger'}, dict(state['writer_profile'], gates={'sources_required': 'yes'})):
            with self.subTest(bad=bad):
                workflow.write_json(layout.path(self.article, 'workflow.json'),
                                    dict(state, writer_profile=bad))
                with self.assertRaises(ValueError):
                    workflow.load(self.article)


class RoleCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-role-cli-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / 'openwrite.yaml').write_text(
            'wechat:\n  accounts:\n    主号: {}\n', encoding='utf-8')

    def cli(self, *args):
        for name in ('openwrite.py', 'workflow.py', 'preferences.py', 'platforms.py',
                     'layout.py', 'writer_roles.py'):
            shutil.copy2(ROOT / name, self.root / name)
        shutil.copytree(ROOT / 'writer_roles', self.root / 'writer_roles', dirs_exist_ok=True)
        return subprocess.run([sys.executable, '-B', str(self.root / 'openwrite.py'), *args],
                              cwd=self.root, capture_output=True, text=True)

    def test_new_persists_constraints_into_brief_and_snapshot(self):
        result = self.cli('new', 'story', '--perspective', 'novelist', '--title', '悬念故事')
        self.assertEqual(result.returncode, 0, result.stderr)
        article = self.root / 'articles/story'
        state = workflow.load(article)
        self.assertEqual(state['writer_profile']['role'], 'novelist')
        brief = (layout.path(article, 'brief.md')).read_text(encoding='utf-8')
        self.assertIn('## 写作约束（角色预设）', brief)
        self.assertIn('允许发挥想象，进行符合逻辑的虚构', brief)
        self.assertIn('视角：小说家', brief)

    def test_status_routes_new_roles_to_generic_skill(self):
        result = self.cli('new', 'flash', '--perspective', 'news')
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.cli('workflow', 'status', str(self.root / 'articles/flash'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('写作视角：新闻记者', result.stdout)
        self.assertIn('openwrite-generic-writer', result.stdout)

    def test_legacy_role_labels_still_work(self):
        result = self.cli('new', 'legacy', '--perspective', 'tech')
        self.assertEqual(result.returncode, 0, result.stderr)
        state = workflow.load(self.root / 'articles/legacy')
        self.assertEqual(state['perspective'], 'tech')
        self.assertEqual(state['writer_profile']['name'], '技术作者')


if __name__ == '__main__':
    unittest.main()