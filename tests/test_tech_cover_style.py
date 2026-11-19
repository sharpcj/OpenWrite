"""Offline style-to-CLI coverage; all artwork and account data are fixtures."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import layout
import workflow
from workflow_fixtures import seed_body

ROOT = Path(__file__).resolve().parents[1]


class TechCoverStyleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-tech-style-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.article = self.root / 'article'
        self.article.mkdir()
        workflow.initialize(self.article, '测试文章', cover_style={'style': 'tech-glow'})
        self.raw = {'id': 'cover', 'role': 'cover', 'output': 'cover.png',
                    'width': 1024, 'height': 432, 'prompt': '检索增强的知识节点，无文字',
                    'text': [], 'overlay': {'title': '科技封面', 'subtitle': 'OpenWrite',
                                            'tagline': '把知识连接起来'}}
        self.runtime = workflow.image_runtime()
        self.save(self.raw)

    def save(self, raw):
        workflow.write_json(layout.path(self.article, 'image-requests.json'),
                            {'version': 1, 'images': [raw]})

    def test_discovery_defaults_overrides_and_no_input_mutation(self):
        styles = self.runtime._cover_styles()
        self.assertIn('tech-glow', styles.list_styles())
        for name in ('tech-glow', '科技发光', '深色科技'):
            design = styles.design_for({'style': name})
            self.assertEqual(design['overlay_defaults']['effect'], 'tech-glow')
            self.assertIn('dark navy', design['instructions'])
        resolved = self.runtime.load_request(self.article, 'cover')
        self.assertEqual(resolved['overlay']['color'], '#ffffff')
        self.assertEqual(resolved['overlay']['panel_alpha'], 205)
        self.assertEqual(resolved['overlay']['position'], 'center-left')
        self.assertEqual(resolved['overlay']['text_width_ratio'], 0.55)
        self.assertIn('深色科技', resolved['style'])
        self.assertEqual(workflow.read_json(layout.path(self.article, 'image-requests.json'))['images'][0], self.raw)
        custom = copy.deepcopy(self.raw)
        custom['overlay'].update(color='#eeeeff', panel_alpha=120)
        self.save(custom)
        resolved = self.runtime.load_request(self.article, 'cover')
        self.assertEqual(resolved['overlay']['color'], '#eeeeff')
        self.assertEqual(resolved['overlay']['panel_alpha'], 120)
        self.assertNotEqual(self.runtime.request_hash(resolved),
                            self.runtime.request_hash(self.runtime._cover_requirement(self.article, self.raw)))
        design = styles.design_for({'style': 'tech-glow', 'visual_style': '科技线稿', 'color_tone': '青绿'})
        self.assertEqual(design['visual_style'], '科技线稿')
        self.assertEqual(design['palette'], ['青绿'])

    def test_bad_effect_parameters_fail_before_backend(self):
        for key, value in (('effect', 'typo'), ('panel_alpha', 999),
                           ('panel_fade_ratio', float('nan')), ('glow_radius', -1),
                           ('glow_color', 'not-a-color'), ('font', '/missing/font.ttf')):
            with self.subTest(key=key):
                raw = copy.deepcopy(self.raw)
                raw['overlay'][key] = value
                self.save(raw)
                with patch.object(self.runtime, 'obtain_backend') as obtain:
                    with self.assertRaises(ValueError):
                        self.runtime.load_request(self.article, 'cover')
                    obtain.assert_not_called()

    def test_real_root_cli_image_review_format_and_style_reset(self):
        # Isolated CLI checkout: no private configuration, no live services.
        cli_root = self.root / 'checkout'
        cli_root.mkdir()
        for name in ('openwrite.py', 'workflow.py', 'preferences.py', 'platforms.py', 'layout.py',
                     'writer_roles.py'):
            shutil.copy2(ROOT / name, cli_root / name)
        shutil.copytree(ROOT / 'writer_roles', cli_root / 'writer_roles')
        shutil.copytree(ROOT / 'skills', cli_root / 'skills',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*token*', '.env*'))
        (cli_root / 'openwrite.yaml').write_text('wechat:\n  accounts:\n    demo: {}\n', encoding='utf-8')
        env = dict(os.environ)

        def cli(*args, ok=True):
            result = subprocess.run([sys.executable, '-B', str(cli_root / 'openwrite.py'), *args],
                                    cwd=cli_root, env=env, capture_output=True, text=True)
            if ok:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            else:
                self.assertNotEqual(result.returncode, 0)
            return result

        cli('new', 'demo', '--cover-style', 'full-bleed-single-title')
        article = cli_root / 'articles/demo'
        cli('workflow', 'cover-style', str(article), '--cover-style', 'tech-glow')
        self.assertEqual(workflow.load(article)['cover_style']['style'], 'tech-glow')
        cli('image', str(article), '--id', 'cover', '--backend', 'file', ok=False)
        seed_body(article)
        workflow.write_json(layout.path(article, 'image-requests.json'),
                            {'version': 1, 'images': [self.raw]})
        base = article / 'process/base-fixture.png'
        Image.new('RGB', (1024, 432), '#203656').save(base)
        cli('image', str(article), '--id', 'cover', '--backend', 'file', '--source', str(base))
        resolved = self.runtime.load_request(article, 'cover')
        report = workflow.read_json(layout.path(article, 'image-results.json'))['images'][0]
        self.assertEqual(report['request_hash'], self.runtime.request_hash(resolved))
        workflow.image_proof(article, resolved)
        cli('workflow', 'complete', str(article), '--step', 'cover', ok=False)
        cli('workflow', 'complete', str(article), '--step', 'cover', '--reviewed',
            '--note', '离线测试合成件的程序验收记录，非真实文章视觉验收')
        cli('workflow', 'cover-style', str(article), '--cover-style', '左文右图', ok=False)
        workflow.write_json(layout.path(article, 'content-images.json'),
                            {'needed': False, 'reason': '测试正文不需要配图'})
        cli('workflow', 'complete', str(article), '--step', 'content')
        cli('workflow', 'finalize', str(article))
        cli('format', str(article), '--theme', 'blueprint-tech')
        self.assertTrue((article / 'article.html').is_file())
        self.assertEqual(workflow.require_publishable(article)['theme'], 'blueprint-tech')
        cli('workflow', 'reset', str(article), '--from', 'cover')
        cli('workflow', 'cover-style', str(article), '--cover-style', 'left-text-right-image')
        self.assertEqual(workflow.load(article)['cover_style']['style'], 'left-text-right-image')


if __name__ == '__main__':
    unittest.main()
