"""Platform adapter registry: shared order, per-platform product specs and gates."""
import json
from pathlib import Path
import tempfile
import unittest

import platforms
import preferences
import workflow

ROOT = Path(__file__).resolve().parents[1]


class RegistryTests(unittest.TestCase):
    def test_registry_covers_every_selectable_platform(self):
        self.assertEqual(set(platforms.REGISTRY), set(preferences.PLATFORM_LABELS))
        for name, profile in platforms.REGISTRY.items():
            with self.subTest(platform=name):
                self.assertEqual(profile['label'], preferences.PLATFORM_LABELS[name])
                for key in ('renderer', 'publisher', 'publisher_entry', 'markdown_artifact',
                            'artifacts', 'cover', 'content_images', 'limits', 'checks', 'writers'):
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

    def test_rednote_writing_pipeline_is_implemented_but_upload_is_not(self):
        profile = platforms.spec('rednote')
        self.assertTrue(profile['implemented'])
        self.assertFalse(profile['publish_implemented'])
        self.assertEqual(profile['format_label'], '组装并保存可发布产物')
        self.assertEqual(profile['limits']['title_chars'], 20)
        self.assertEqual((profile['cover']['width'], profile['cover']['height']), (1080, 1440))
        self.assertEqual(profile['cover']['output'], 'xhs-01-cover.png')
        self.assertEqual(profile['content_size'], {'width': 1080, 'height': 1440})
        # 张数动态：必需正文卡片，但不固定上下限。
        self.assertTrue(profile['content_images']['required'])
        self.assertEqual(profile['content_images']['min'], 1)
        self.assertIsNone(profile['content_images']['max'])
        self.assertEqual(profile['markdown_artifact'], 'note.md')
        self.assertIsNone(profile['rendered_artifact'])
        self.assertEqual(profile['renderer'], 'openwrite-images')
        self.assertFalse(profile['checks']['code_blocks_converted'])
        # 未取得权威来源的项不得进入强制 limits。
        self.assertEqual(set(profile['unverified']), {'desc_chars', 'max_images'})
        self.assertNotIn('desc_chars', profile['limits'])
        self.assertNotIn('max_images', profile['limits'])

    def test_step_labels_are_platform_specific(self):
        wechat = platforms.step_labels({'platform': 'wechat'})
        rednote = platforms.step_labels({'platform': 'rednote'})
        self.assertEqual(wechat[:-1], rednote[:-1])
        self.assertEqual(wechat[-1], '排版并保存可发布产物')
        self.assertEqual(rednote[-1], '组装并保存可发布产物')

    def test_implemented_platforms_ship_their_skills(self):
        for name, profile in platforms.REGISTRY.items():
            if not profile['implemented']:
                continue
            skills = [profile['renderer'], *profile['writers'].values()]
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
        workflow.write_json(self.article / 'sources.json', {'version': 1, 'sources': [
            {'id': 's1', 'title': '用户资料', 'kind': 'user', 'content': '实际资料'},
        ]})

    def test_wechat_pipeline_is_available(self):
        self.start('wechat')
        profile = platforms.require_pipeline(workflow.load(self.article))
        self.assertEqual(profile['label'], '微信')
        workflow.complete(self.article, 'search')

    def test_rednote_can_write_but_upload_adapter_is_still_missing(self):
        self.start('rednote')
        state = workflow.load(self.article)
        self.assertEqual(state['platform'], 'rednote')
        # 写作门禁已放行。
        self.assertEqual(platforms.require_pipeline(state)['label'], '小红书')
        workflow.complete(self.article, 'search')
        # 上传适配器未实现，publish 仍被拒绝。
        with self.assertRaises(ValueError) as error:
            platforms.require_publish_adapter(workflow.load(self.article))
        self.assertIn('上传适配器尚未实现', str(error.exception))
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
