"""Cover-designer theme presets: discovery, layout matching and design resolution."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'cover_themes_test', ROOT / 'skills/wechat-cover-designer/scripts/cover_themes.py')
cover_themes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cover_themes)


class CoverThemeTests(unittest.TestCase):
    def test_list_and_load(self):
        self.assertIn('left-text-right-image', cover_themes.list_themes())
        theme = cover_themes.load_theme('left-text-right-image')
        self.assertEqual(theme['name'], '左文右图·暖色人物')
        with self.assertRaises(ValueError):
            cover_themes.load_theme('no-such-theme')

    def test_find_by_layout_matches_name_and_aliases(self):
        for layout in ('左文右图', 'left-text-right-image'):
            theme = cover_themes.find_by_layout(layout)
            self.assertIsNotNone(theme, layout)
            self.assertEqual(theme['name'], '左文右图·暖色人物')
        self.assertIsNone(cover_themes.find_by_layout('居中标题'))
        self.assertIsNone(cover_themes.find_by_layout(''))

    def test_design_for_known_layout(self):
        design = cover_themes.design_for(
            {'layout': '左文右图', 'visual_style': '温暖插画', 'color_tone': '暖黄奶油色'})
        self.assertEqual(design['theme'], '左文右图·暖色人物')
        self.assertEqual(design['style'], '温暖插画')
        self.assertEqual(design['palette'], ['暖黄奶油色'])
        self.assertIn('smooth continuous warm gradient', design['instructions'])
        self.assertIn('right ~50%', design['instructions'])
        self.assertIn('left ~45%', design['instructions'])
        self.assertEqual(design['overlay_defaults']['position'], 'center-left')
        self.assertEqual(design['overlay_defaults']['text_width_ratio'], 0.45)
        self.assertFalse(design['overlay_defaults']['scrim'])
        self.assertEqual(design['overlay_defaults']['effect'], 'warm-editorial')
        self.assertEqual(design['overlay_defaults']['font_size'], 62)
        self.assertEqual(design['overlay_defaults']['subtitle_size'], 44)
        self.assertEqual(design['overlay_defaults']['color'], '#583720')
        self.assertIn('extending to the bottom edge', design['instructions'])
        self.assertNotIn('never touching', design['instructions'])
        self.assertEqual(design['positions'], ['top-left', 'center-left', 'bottom-left'])
        self.assertEqual(design['levels'], ['title', 'subtitle', 'tagline'])

    def test_single_title_theme_declares_one_level(self):
        design = cover_themes.design_for({'layout': '全幅单标题'})
        self.assertEqual(design['levels'], ['title'])
        self.assertIn('single big bold title', design['instructions'])

    def test_single_title_theme_is_full_bleed_and_centered(self):
        design = cover_themes.design_for({'theme': 'full-bleed-single-title'})
        self.assertEqual(design['theme'], '全幅插画·居中标题')
        self.assertEqual(design['levels'], ['title'])
        self.assertEqual(design['overlay_defaults'],
                         {'position': 'center', 'text_width_ratio': 0.8, 'scrim': False})
        self.assertEqual(design['positions'], ['center', 'top-center', 'bottom-center'])
        self.assertIn('the full ~100%', design['instructions'])
        self.assertIn('the full ~80%', design['instructions'])
        self.assertNotIn('the right ~50%', design['instructions'])

    def test_single_title_legacy_aliases_still_resolve(self):
        for layout in ('left-text-single-title', '左文单标题'):
            design = cover_themes.design_for({'theme': layout})
            self.assertEqual(design['theme'], '全幅插画·居中标题')
            self.assertEqual(design['levels'], ['title'])
            self.assertEqual(design['overlay_defaults']['position'], 'center')

    def test_theme_field_takes_precedence_over_layout(self):
        design = cover_themes.design_for({'theme': 'full-bleed-single-title', 'layout': '左文右图'})
        self.assertEqual(design['levels'], ['title'])
        alias = cover_themes.design_for({'theme': '左文右图'})
        self.assertEqual(alias['theme'], '左文右图·暖色人物')

    def test_design_for_custom_layout_falls_back(self):
        design = cover_themes.design_for({'layout': '居中标题', 'color_tone': '青绿渐变'})
        self.assertIsNone(design['theme'])
        self.assertEqual(design['instructions'], '居中标题')
        self.assertEqual(design['overlay_defaults'], {})
        self.assertEqual(design['palette'], ['青绿渐变'])

    def test_design_for_empty_layout(self):
        design = cover_themes.design_for({'visual_style': '科技线稿'})
        self.assertIsNone(design['theme'])
        self.assertEqual(design['instructions'], '')
        self.assertEqual(design['style'], '科技线稿')


if __name__ == '__main__':
    unittest.main()
