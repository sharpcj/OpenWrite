"""Platform adapter registry: shared order, per-platform product specs and gates."""
import layout
import json
from pathlib import Path
import tempfile
import unittest

import platforms
import preferences
import workflow
import writer_roles

ROOT = Path(__file__).resolve().parents[1]


class RegistryTests(unittest.TestCase):
    def test_registry_covers_every_selectable_platform(self):
        self.assertEqual(set(platforms.REGISTRY), set(preferences.PLATFORM_LABELS))
        for name, profile in platforms.REGISTRY.items():
            with self.subTest(platform=name):
                self.assertEqual(profile['label'], preferences.PLATFORM_LABELS[name])
                for key in ('renderer', 'publisher', 'publisher_entry', 'markdown_artifact',
                            'artifacts', 'cover', 'content_images', 'limits', 'checks'):
                    self.assertIn(key, profile)

    def test_wechat_specs_match_the_previous_hardcoded_limits(self):
        profile = platforms.spec('wechat')
        self.assertTrue(profile['implemented'])
        self.assertEqual(profile['limits'], {'title_chars': 64, 'title_bytes': 192,
                                             'author_bytes': 20, 'digest_bytes': 120,
                                             'cover_bytes': 2 * 1024 * 1024})
        self.assertEqual(profile['cover'], {'id': 'cover', 'output': 'cover.png',
                                            'width': 1024, 'height': 432})
        self.assertEqual(profile['artifacts'], ['article.md', 'article.html', 'cover.png'])
        self.assertEqual(profile['optional_artifacts'], ['closing.md'])
        self.assertFalse(profile['content_images']['required'])
        self.assertTrue(profile['checks']['code_blocks_converted'])
        self.assertEqual(profile['author_key'], 'WeChatAuthor')

    def test_rednote_writing_and_upload_adapters_are_implemented(self):
        profile = platforms.spec('rednote')
        self.assertTrue(profile['implemented'])
        self.assertTrue(profile['publish_implemented'])
        self.assertEqual(profile['format_label'], '生成可发布交付件')
        self.assertEqual(profile['limits']['title_chars'], 20)
        self.assertEqual((profile['cover']['width'], profile['cover']['height']), (1080, 1440))
        self.assertEqual(profile['cover']['output'], 'xhs-01-cover.png')
        self.assertEqual(profile['content_size'], {'width': 1080, 'height': 1440})
        # 张数动态：必需正文卡片；封面 + 内容合计不超过平台 18 张上限。
        self.assertTrue(profile['content_images']['required'])
        self.assertEqual(profile['content_images']['min'], 1)
        self.assertEqual(profile['content_images']['max'], 17)
        self.assertEqual(profile['markdown_artifact'], 'note.md')
        self.assertIsNone(profile['rendered_artifact'])
        self.assertEqual(profile['renderer'], 'openwrite-images')
        self.assertFalse(profile['checks']['code_blocks_converted'])
        # 常规图文笔记规格已由多个公开来源核实并写入 limits。
        self.assertEqual(profile['unverified'], [])
        self.assertEqual(profile['limits']['desc_chars'], 1000)
        self.assertEqual(profile['limits']['max_images'], 18)

    def test_step_labels_share_unified_format_label(self):
        wechat = platforms.step_labels({'platform': 'wechat'})
        rednote = platforms.step_labels({'platform': 'rednote'})
        self.assertEqual(wechat[:-1], rednote[:-1])
        self.assertEqual(wechat[-1], '生成可发布交付件')
        self.assertEqual(rednote[-1], '生成可发布交付件')

    def test_implemented_platforms_ship_their_skills(self):
        for name, profile in platforms.REGISTRY.items():
            if not profile['implemented']:
                continue
            skills = [profile['renderer']]
            # 写作 Skill 接线来自角色预设。
            for role in writer_roles.list_roles():
                skill = writer_roles.load_role(role)['skills'].get(name)
                if skill:
                    skills.append(skill)
            if profile.get('publish_implemented'):
                skills.append(profile['publisher'])
            for skill in skills:
                with self.subTest(platform=name, skill=skill):
                    self.assertTrue((ROOT / 'skills' / skill / 'SKILL.md').is_file())

    def test_unknown_platform_is_rejected(self):
        with self.assertRaises(ValueError):
            platforms.spec('weibo')

    def test_writer_skill_follows_platform_and_perspective(self):
        self.assertEqual(platforms.writer_skill({'platform': 'wechat', 'perspective': 'blogger'}),
                         'wechat-blogger-writer')
        self.assertEqual(platforms.writer_skill({'platform': 'wechat', 'perspective': 'product'}),
                         'wechat-product-manager-writer')
        self.assertEqual(platforms.writer_skill({'platform': 'wechat', 'perspective': 'news'}),
                         'openwrite-generic-writer')
        self.assertEqual(platforms.writer_skill({'platform': 'wechat', 'perspective': 'novelist'}),
                         'openwrite-generic-writer')
        self.assertEqual(platforms.writer_skill({'platform': 'rednote', 'perspective': 'blogger'}),
                         'rednote-note-writer')
        with self.assertRaises(ValueError):
            platforms.writer_skill({'platform': 'rednote', 'perspective': 'tech'})

    def test_legacy_task_without_platform_defaults_to_wechat(self):
        self.assertEqual(platforms.for_state({'type': 'tech'})['label'], '微信')


class PipelineGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-platforms-')
        self.addCleanup(self.tmp.cleanup)
        self.article = Path(self.tmp.name).resolve()

    def start(self, platform):
        workflow.initialize(self.article, '测试', 'blogger', platform, {})
        workflow.write_json(layout.path(self.article, 'sources.json'), {'version': 1, 'sources': [
            {'id': 's1', 'title': '用户资料', 'kind': 'user', 'content': '实际资料'},
        ]})

    def test_wechat_pipeline_is_available(self):
        self.start('wechat')
        profile = platforms.require_pipeline(workflow.load(self.article))
        self.assertEqual(profile['label'], '微信')
        workflow.complete(self.article, 'search')

    def test_rednote_write_and_upload_adapters_are_available(self):
        self.start('rednote')
        state = workflow.load(self.article)
        self.assertEqual(state['platform'], 'rednote')
        # 写作门禁已放行。
        self.assertEqual(platforms.require_pipeline(state)['label'], '小红书')
        workflow.complete(self.article, 'search')
        # P1 发布适配器已接入。
        profile = platforms.require_publish_adapter(workflow.load(self.article))
        self.assertEqual(profile['publisher'], 'rednote-publisher')
        self.assertEqual(workflow.load(self.article)['platform'], 'rednote')

    def test_wechat_upload_adapter_is_available(self):
        self.start('wechat')
        self.assertEqual(platforms.require_publish_adapter(workflow.load(self.article))['publisher'],
                         'wechat-draft-publisher')

    def test_limits_are_read_from_the_registry(self):
        self.start('wechat')
        self.assertEqual(workflow.platforms.limits(workflow.load(self.article))['title_chars'], 64)


if __name__ == '__main__':
    unittest.main()
