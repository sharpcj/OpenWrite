"""Offline pixel regressions for the opt-in legacy technology cover renderer."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'skills/openwrite-images/scripts/cover_text.py'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cover = load(SCRIPT, 'tech_cover_under_test')


def reference_glow(base, xy, text, font, fill, glow, glow_radius=10):
    # Frozen algorithm from the read-only legacy cover_text_overlay.py.
    sl = Image.new('RGBA', base.size, (0, 0, 0, 0))
    ImageDraw.Draw(sl).text((xy[0] + 3, xy[1] + 5), text, font=font, fill=(0, 0, 0, 180))
    sl = sl.filter(ImageFilter.GaussianBlur(3))
    gl1 = Image.new('RGBA', base.size, (0, 0, 0, 0))
    ImageDraw.Draw(gl1).text(xy, text, font=font, fill=glow + (255,))
    gl1 = gl1.filter(ImageFilter.GaussianBlur(glow_radius))
    gl2 = gl1.filter(ImageFilter.GaussianBlur(glow_radius // 2 or 1))
    ml = Image.new('RGBA', base.size, (0, 0, 0, 0))
    ImageDraw.Draw(ml).text(xy, text, font=font, fill=fill)
    out = Image.alpha_composite(base, sl)
    out = Image.alpha_composite(out, gl1)
    out = Image.alpha_composite(out, gl2)
    return Image.alpha_composite(out, ml)


class TechCoverRenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name) / 'base.png'
        self.output = Path(self.temp.name) / 'output.png'
        self.size = (1024, 432)
        Image.new('RGB', self.size, (65, 95, 135)).save(self.base)
        self.overlay = {'effect': 'tech-glow', 'title': '科技未来',
                        'subtitle': 'Build Better AI', 'tagline': '探索新的可能'}

    def render(self, overlay=None):
        cover.render(self.base, self.output, self.overlay if overlay is None else overlay, *self.size)
        with Image.open(self.output) as image:
            return image.copy()

    def test_double_glow_matches_frozen_legacy_pixels(self):
        base = Image.new('RGBA', (320, 180), (90, 110, 140, 255))
        font = cover._tech_font({}, 'subtitle_font', 36)
        for radius in (0, 8, 14):
            args = (base, (32, 40), 'Tech AI', font, (140, 215, 255, 255), (80, 160, 230), radius)
            with self.subTest(radius=radius):
                self.assertEqual(cover._tech_glow_text(*args).tobytes(), reference_glow(*args).tobytes())

    def test_full_render_matches_legacy_composites_without_decorative_lines(self):
        # Independent typesetting coordinates for this single-line fixture.
        fonts = [cover._tech_font({}, key, size) for key, size in
                 (('font', 92), ('subtitle_font', 28), ('tagline_font', 26))]
        texts = [self.overlay[k] for k in ('title', 'subtitle', 'tagline')]
        boxes = [font.getbbox(text) for font, text in zip(fonts, texts)]
        heights = [b[3] - b[1] for b in boxes]
        y = (432 - sum(heights) - 42 - 14) // 2 - 6
        expected = Image.new('RGBA', self.size, (65, 95, 135, 255))
        panel = Image.new('RGBA', self.size)
        draw = ImageDraw.Draw(panel)
        for x in range(int(1024 * .55)):
            t = x / int(1024 * .55)
            draw.line([(x, 0), (x, 432)], fill=(6, 12, 38, int(205 * (1 - t * t * (3 - 2 * t)))))
        expected = Image.alpha_composite(expected, panel)
        for level, (font, text, bbox) in enumerate(zip(fonts, texts, boxes)):
            xy = (64 - bbox[0], y - bbox[1])
            if level < 2:
                expected = reference_glow(expected, xy, text, font,
                                          (255, 255, 255, 255) if level == 0 else (140, 215, 255, 255),
                                          (110, 170, 255) if level == 0 else (80, 160, 230),
                                          14 if level == 0 else 8)
            else:
                draw = ImageDraw.Draw(expected)
                draw.text((xy[0] + 1, xy[1] + 2), text, font=font, fill=(0, 0, 0, 160))
                draw.text(xy, text, font=font, fill=(210, 215, 230, 240))
            y += heights[level] + (42 if level == 0 else 14)
        self.assertEqual(self.render().tobytes(), expected.convert('RGB').tobytes())

    def test_smoothstep_panel_has_no_solid_segment_or_horizontal_lines(self):
        image = self.render({'effect': 'tech-glow', 'title': ''})
        # With no text, every row must match: decorative horizontal rules fail.
        row = image.crop((0, 0, 1024, 1)).tobytes()
        for y in (1, 100, 215, 431):
            self.assertEqual(row, image.crop((0, y, 1024, y + 1)).tobytes())
        for x in (0, 64, 150, 300, 562, 563, 900):
            t = x / 563
            alpha = int(205 * (1 - t * t * (3 - 2 * t))) if x < 563 else 0
            pixel = Image.alpha_composite(Image.new('RGBA', (1, 1), (65, 95, 135, 255)),
                                         Image.new('RGBA', (1, 1), (6, 12, 38, alpha))).convert('RGB').getpixel((0, 0))
            self.assertEqual(image.getpixel((x, 50)), pixel)
        self.assertNotEqual(image.getpixel((0, 0)), image.getpixel((150, 0)))

    def test_actual_ink_bounds_offsets_fonts_and_left_positions(self):
        tops = []
        for position in ('top-left', 'center-left', 'bottom-left'):
            overlay = dict(self.overlay, position=position, vertical_offset=0)
            rows = cover._tech_layout(overlay, *self.size)
            tops.append(rows[0]['xy'][1] + rows[0]['bbox'][1])
            self.assertNotEqual(rows[0]['font'].path, rows[1]['font'].path)
            self.assertNotEqual(rows[0]['font'].path, rows[2]['font'].path)
            for row in rows:
                ink = Image.new('L', self.size)
                ImageDraw.Draw(ink).text(row['xy'], row['text'], font=row['font'], fill=255)
                bounds = ink.getbbox()
                self.assertIsNotNone(bounds)
                assert bounds is not None
                left, top, right, bottom = bounds
                self.assertGreaterEqual(left, 64)
                self.assertLessEqual(right, 64 + int(1024 * .55))
                self.assertGreaterEqual(top, int(432 * .0625))
                self.assertLessEqual(bottom, 432 - int(432 * .0625))
            self.render(overlay)
        self.assertEqual(tops, sorted(tops))
        self.assertEqual(len(set(tops)), 3)

    def test_long_chinese_and_unbroken_english_wrap_and_shrink(self):
        for text in ('人工智能改变未来科技世界' * 5, 'Supercalifragilisticexpialidocious' * 4):
            overlay = dict(self.overlay, title=text)
            rows = cover._tech_layout(overlay, *self.size)
            title_rows = [row for row in rows if row['level'] == 0]
            self.assertGreater(len(title_rows), 1)
            self.assertLess(title_rows[0]['font'].size, 92)
            self.assertEqual(''.join(row['text'] for row in title_rows), text)
            for row in rows:
                self.assertLessEqual(row['bbox'][2] - row['bbox'][0], int(1024 * .55))
                self.assertLessEqual(row['xy'][1] + row['bbox'][3], 432 - int(432 * .0625))
            self.render(overlay)

    def test_overlay_overrides_geometry_colors_and_explicit_fonts(self):
        latin = str(cover._tech_font({}, 'subtitle_font', 24).path)
        overlay = dict(self.overlay, font=latin, subtitle_font=latin, tagline_font=latin,
                       title='Title', subtitle='Subtitle', tagline='Tagline',
                       font_size=40, subtitle_size=20, tagline_size=16,
                       margin_ratio=.1, text_width_ratio=.4, title_subtitle_gap=20,
                       subtitle_tagline_gap=7, vertical_offset=9,
                       color='#ff0000', subtitle_color=[0, 255, 0], tagline_color=[0, 0, 255, 255],
                       glow_color=[1, 2, 3], subtitle_glow_color='#040506',
                       panel_color='#070809', panel_alpha=0, panel_fade_ratio=.8,
                       glow_radius=3, subtitle_glow_radius=2)
        cover.validate_tech_overlay(overlay)
        rows = cover._tech_layout(overlay, *self.size)
        self.assertEqual([row['font'].size for row in rows], [40, 20, 16])
        self.assertTrue(all(row['font'].path == latin for row in rows))
        self.assertEqual(rows[1]['y'] - rows[0]['y'] - (rows[0]['bbox'][3] - rows[0]['bbox'][1]), 20)
        self.assertEqual(rows[2]['y'] - rows[1]['y'] - (rows[1]['bbox'][3] - rows[1]['bbox'][1]), 7)
        block_height = rows[-1]['y'] + rows[-1]['bbox'][3] - rows[-1]['bbox'][1]
        self.assertEqual(rows[0]['xy'][1] + rows[0]['bbox'][1], (432 - block_height) // 2 + 9)
        self.assertEqual(rows[0]['xy'][0] + rows[0]['bbox'][0], 102)
        image = self.render(overlay)
        self.assertEqual(image.getpixel((1000, 0)), (65, 95, 135))
        colors = {color for _, color in image.getcolors(1024 * 432) or []}
        for color in ((255, 0, 0), (0, 255, 0), (0, 0, 255)):
            self.assertIn(color, colors)

    def test_chinese_subtitle_uses_cjk_font(self):
        rows = cover._tech_layout(dict(self.overlay, subtitle='中文副标题'), *self.size)
        self.assertEqual(rows[0]['font'].path, rows[1]['font'].path)
        self.render(dict(self.overlay, subtitle='中文副标题'))

    def test_impossibly_long_text_fails_clearly(self):
        with self.assertRaisesRegex(ValueError, '最小字号'):
            cover._tech_layout(dict(self.overlay, title='测' * 1500), *self.size)

    def test_validation_precedes_file_io_and_rejects_invalid_fields(self):
        bad_values = [('panel_alpha', float('nan')), ('glow_radius', float('inf')),
                      ('font_size', True), ('font_size', .5), ('text_width_ratio', 1),
                      ('margin_ratio', -.1), ('panel_fade_ratio', 0),
                      ('vertical_offset', '6'), ('subtitle_tagline_gap', -1),
                      ('font', ''), ('subtitle_font', 123), ('tagline_font', 'bad\x00font'),
                      ('color', [1, 2, 256]), ('glow_color', 'not-a-color'),
                      ('panel_color', [True, 2, 3]), ('position', 'center')]
        for key, value in bad_values:
            with self.subTest(key=key, value=value):
                with self.assertRaisesRegex(ValueError, key):
                    cover.render('does-not-exist.png', self.output,
                                 dict(self.overlay, **{key: value}), *self.size)
        cover.validate_tech_overlay(dict(self.overlay, panel_alpha=0, color='#ffffff',
                                         subtitle_color=[1, 2, 3], tagline_color=[1, 2, 3, 4]))

    def test_explicit_missing_or_corrupt_fonts_never_silently_fallback(self):
        corrupt = Path(self.temp.name) / 'corrupt.ttf'
        corrupt.write_text('not a font')
        for key in ('font', 'subtitle_font', 'tagline_font'):
            for path in ('/missing/font.ttf', str(corrupt)):
                with self.subTest(key=key, path=path):
                    with self.assertRaisesRegex(ValueError, key + ' 显式字体无效'):
                        self.render(dict(self.overlay, **{key: path}))

    def test_no_available_fonts_has_actionable_error(self):
        with patch.object(Path, 'is_file', return_value=False):
            with self.assertRaisesRegex(ValueError, 'overlay.font'):
                cover._tech_font({}, 'font', 92)
            with self.assertRaisesRegex(ValueError, 'overlay.subtitle_font'):
                cover._tech_font({}, 'subtitle_font', 28)

    def test_warm_plain_renderer_is_pixel_unchanged(self):
        overlay = {'title': '暖色封面', 'subtitle': 'Warm cover', 'tagline': '简洁文字',
                   'position': 'center-left', 'color': '#452b18', 'tagline_color': '#796348',
                   'scrim': False, 'font_size': 64, 'subtitle_size': 28, 'tagline_size': 24}
        layout = cover._layout(overlay, *self.size)
        expected = Image.new('RGBA', self.size, (65, 95, 135, 255))
        draw = ImageDraw.Draw(expected)
        y = (432 - layout['block_h']) // 2
        for line in layout['title_lines']:
            draw.text((layout['margin'], y), line, font=layout['title_font'], fill=overlay['color'],
                      stroke_width=max(1, layout['size'] // 32), stroke_fill=overlay['color'])
            y += layout['title_lh']
        y += layout['gap']
        for line in layout['sub_lines']:
            draw.text((layout['margin'], y), line, font=layout['sub_font'], fill=overlay['color'])
            y += layout['sub_lh']
        y += layout['gap2']
        for line in layout['tag_lines']:
            draw.text((layout['margin'], y), line, font=layout['tag_font'], fill=overlay['tagline_color'])
            y += layout['tag_lh']
        self.assertEqual(self.render(overlay).tobytes(), expected.convert('RGB').tobytes())
        self.assertEqual(self.render(dict(overlay, effect='plain')).tobytes(), expected.convert('RGB').tobytes())


if __name__ == '__main__':
    unittest.main()
