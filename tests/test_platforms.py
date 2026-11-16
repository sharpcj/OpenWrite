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

    def test_rednote_specs_are_recorded_but_pipeline_is_not_implemented(self):
        profile = platforms.spec('rednote')
        self.assertFalse(profile['implemented'])
        self.assertEqual(profile['limits']['title_chars'], 20)
        self.assertEqual((profile['cover']['width'], profile['cover']['height']), (1080, 1440))
        self.assertEqual(profile['content_size'], {'width': 1080, 'height': 1440})
        self.assertTrue(profile['content_images']['required'])
        self.assertEqual((profile['content_images']['min'], profile['content_images']['max']), (4, 8))
        self.assertEqual(profile['markdown_artifact'], 'note.md')
        self.assertIsNone(profile['rendered_artifact'])
        self.assertFalse(profile['checks']['code_blocks_converted'])
        # Unverified platform limits must stay out of the enforced limits.
        self.assertIn('desc_chars', profile['unverified'])
        self.assertNotIn('desc_chars', profile['limits'])

    def test_implemented_platforms_ship_their_skills(self):
        for name, profile in platforms.REGISTRY.items():
            if not profile['implemented']:
                continue
            for skill in [profile['renderer'], profile['publisher'], *profile['writers'].values()]:
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

    def test_rednote_selection_is_saved_but_every_gate_rejects_it(self):
        self.start('rednote')
        state = workflow.load(self.article)
        self.assertEqual(state['platform'], 'rednote')
        with self.assertRaises(ValueError) as error:
            platforms.require_pipeline(state)
        self.assertIn('小红书创作与发布适配尚未实现', str(error.exception))
        for action in (lambda: workflow.complete(self.article, 'search'),
                       lambda: workflow.require_image_stage(self.article, 'cover'),
                       lambda: workflow.require_format_stage(self.article),
                       lambda: workflow.require_finished(self.article)):
            with self.subTest(action=action):
                with self.assertRaises(ValueError):
                    action()
        # The saved choice itself stays readable and unchanged.
        self.assertEqual(workflow.load(self.article)['platform'], 'rednote')

    def test_limits_are_read_from_the_registry(self):
        self.start('wechat')
        self.assertEqual(workflow.platforms.limits(workflow.load(self.article))['title_chars'], 64)


if __name__ == '__main__':
    unittest.main()
