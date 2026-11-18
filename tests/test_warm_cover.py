"""Reference-inspired warm layout: real pixels and offline image CLI integration."""
import copy
from argparse import Namespace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw
import layout
import workflow
from workflow_fixtures import seed_body


class WarmCoverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-warm-cover-')
        self.addCleanup(self.tmp.cleanup)
        self.article = Path(self.tmp.name)
        workflow.initialize(self.article, '测试文章', cover_style={'theme': 'left-text-right-image'})
        self.runtime = workflow.image_runtime()
        self.renderer = self.runtime.load_module('warm_cover_test', 'cover_text.py')
        self.raw = {'id': 'cover', 'role': 'cover', 'output': 'cover.png', 'width': 1024,
                    'height': 432, 'prompt': '右侧贴底生活插画，无文字', 'text': [],
                    'overlay': {'title': 'VideoReel', 'subtitle': '不会剪辑，\n能做宣传视频吗？',
                                'tagline': '模板制作 · 先看用途，再看限制'}}
        self.save(self.raw)
        self.base = self.article / 'base.png'
        Image.new('RGB', (1024, 432), '#fff7df').save(self.base)

    def save(self, raw):
        workflow.write_json(layout.path(self.article, 'image-requests.json'), {'version': 1, 'images': [raw]})

    def resolved(self):
        return self.runtime.load_request(self.article, 'cover')

    def test_defaults_and_three_independent_faces(self):
        overlay = self.resolved()['overlay']
        self.assertEqual(overlay['effect'], 'warm-editorial')
        self.assertEqual(overlay['color'], '#583720')
        self.assertEqual(overlay['subtitle_color'], '#483326')
        rows = self.renderer._editorial_layout(overlay, 1024, 432)
        self.assertEqual([row['text'] for row in rows],
                         ['VideoReel', '不会剪辑，', '能做宣传视频吗？', '模板制作 · 先看用途，再看限制'])
        self.assertEqual([row['font'].size for row in rows], [62, 44, 44, 22])
        self.assertNotEqual(rows[0]['font'].path, rows[1]['font'].path)
        self.assertNotEqual(rows[1]['font'].path, rows[3]['font'].path)
        for row in rows:
            self.assertEqual(row['xy'][0] + row['bbox'][0], 48)
            self.assertLessEqual(row['xy'][0] + row['bbox'][2], 48 + 460)
        self.assertEqual(self.resolved()['palette'], ['奶油白到浅杏橙的连续渐变'])

    def test_clean_pixels_no_glow_shadow_scrim_stroke_or_decorations(self):
        overlay = dict(self.resolved()['overlay'], scrim=True)
        expected = Image.open(self.base).convert('RGBA')
        draw = ImageDraw.Draw(expected)
        colors = [overlay['color'], overlay['subtitle_color'], overlay['tagline_color']]
        for row in self.renderer._editorial_layout(overlay, 1024, 432):
            draw.text(row['xy'], row['text'], font=row['font'], fill=colors[row['level']])
        output = self.article / 'clean.png'
        self.renderer.render(self.base, output, overlay, 1024, 432)
        with Image.open(output) as actual:
            self.assertEqual(actual.tobytes(), expected.convert('RGB').tobytes())
        # Pixel equality above includes all untouched background: no hidden panel or line.

    def test_overrides_and_explicit_font_paths(self):
        raw = copy.deepcopy(self.raw)
        raw['overlay'].update(color='#112233', subtitle_color='#223344', tagline_color='#334455',
                              title_subtitle_gap=12, subtitle_tagline_gap=16, line_gap=4,
                              font_size=50, subtitle_size=32, tagline_size=18, margin_ratio=.06)
        self.save(raw)
        overlay = self.resolved()['overlay']
        rows = self.renderer._editorial_layout(overlay, 1024, 432)
        self.assertEqual(rows[0]['font'].size, 50)
        self.assertEqual(rows[1]['y'] - rows[0]['y'] - rows[0]['bbox'][3] + rows[0]['bbox'][1], 12)
        self.assertEqual(rows[2]['y'] - rows[1]['y'] - rows[1]['bbox'][3] + rows[1]['bbox'][1], 4)
        explicit = dict(overlay, font=rows[1]['font'].path, subtitle_font=rows[0]['font'].path)
        swapped = self.renderer._editorial_layout(explicit, 1024, 432)
        self.assertEqual(swapped[0]['font'].path, rows[1]['font'].path)
        self.assertEqual(swapped[1]['font'].path, rows[0]['font'].path)

    def test_long_text_cjk_headline_and_latin_subtitle_fit(self):
        for title, subtitle in (('普通用户也能制作视频' * 3, 'Make videos with templates'),
                                ('VeryLongBrandName' * 5, '中文卖点' * 10)):
            overlay = dict(self.resolved()['overlay'], title=title, subtitle=subtitle)
            rows = self.renderer._editorial_layout(overlay, 1024, 432)
            self.assertEqual(''.join(row['text'] for row in rows if row['level'] == 0), title)
            for row in rows:
                self.assertGreaterEqual(row['xy'][0] + row['bbox'][0], 48)
                self.assertLessEqual(row['xy'][0] + row['bbox'][2], 508)
                self.assertGreaterEqual(row['xy'][1] + row['bbox'][1], 20)
                self.assertLessEqual(row['xy'][1] + row['bbox'][3], 412)

    def test_title_only_does_not_require_unused_fonts(self):
        overlay = dict(self.resolved()['overlay'], subtitle='', tagline='',
                       subtitle_font='/missing.ttf', tagline_font='/missing.ttf')
        self.assertEqual(len(self.renderer._editorial_layout(overlay, 1024, 432)), 1)

    def test_bad_parameters_and_missing_fonts_fail_before_backend(self):
        for key, value in (('line_gap', float('nan')), ('line_gap', -1),
                           ('subtitle_color', 'bad-color'), ('font', '/missing.ttf')):
            with self.subTest(key=key):
                raw = copy.deepcopy(self.raw)
                raw['overlay'][key] = value
                self.save(raw)
                with patch.object(self.runtime, 'obtain_backend') as backend:
                    with self.assertRaises(ValueError):
                        self.runtime.produce(Namespace(article=str(self.article), id='cover',
                            backend='file', source=str(self.base), profile=None, timeout=10,
                            fit='exact', overwrite=False))
                    backend.assert_not_called()

    def test_root_cli_uses_warm_theme_and_enforces_stage(self):
        import subprocess
        import sys
        root = Path(__file__).resolve().parents[1]
        command = [sys.executable, '-B', str(root / 'openwrite.py'), 'image', str(self.article),
                   '--id', 'cover', '--backend', 'file', '--source', str(self.base)]
        blocked = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn('当前步骤', blocked.stderr)
        self.assertFalse((self.article / 'cover.png').exists())
        seed_body(self.article)
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        effective = self.resolved()
        self.assertEqual(effective['overlay']['effect'], 'warm-editorial')
        workflow.image_proof(self.article, effective)

    def test_real_image_proof_then_modified_layout_invalidates_cover(self):
        seed_body(self.article)
        args = Namespace(article=str(self.article), id='cover', backend='file', source=str(self.base),
                         profile=None, timeout=10, fit='exact', overwrite=False)
        report = self.runtime.produce(args)
        request = self.resolved()
        self.assertEqual(report['request_hash'], self.runtime.request_hash(request))
        workflow.image_proof(self.article, request)
        workflow.complete(self.article, 'cover', reviewed=True, note='离线测试合成件的程序验收记录')
        raw = copy.deepcopy(self.raw)
        raw['overlay']['line_gap'] = 16
        self.save(raw)
        stale = workflow.stale_step(self.article, workflow.load(self.article))
        self.assertIsNotNone(stale)
        assert stale is not None
        self.assertEqual(stale[0], 'cover')
        with self.assertRaises(ValueError):
            workflow.checked(self.article)


if __name__ == '__main__':
    unittest.main()
