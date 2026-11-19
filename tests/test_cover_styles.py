"""Three independent cover dimensions, task snapshots and left/right text safety."""
import layout
from argparse import Namespace
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from PIL import Image, ImageChops, ImageDraw
import preferences
import workflow


ROOT = Path(__file__).resolve().parents[1]
STYLE = {'layout': '左文右图', 'visual_style': '温暖插画', 'color_tone': '暖黄奶油色'}


class CoverStyleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-cover-style-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.config = self.root / preferences.CONFIG_NAME
        self.config.write_text('wechat:\n  accounts:\n    主号:\n      cover:\n'
                               '        layout: 左文右图\n'
                               '        visual_style: 温暖插画\n'
                               '        color_tone: 暖黄奶油色\n', encoding='utf-8')

    def cli(self, *args):
        for name in ('openwrite.py', 'workflow.py', 'preferences.py', 'platforms.py', 'layout.py',
                     'writer_roles.py'):
            shutil.copy2(ROOT / name, self.root / name)
        shutil.copytree(ROOT / 'writer_roles', self.root / 'writer_roles', dirs_exist_ok=True)
        return subprocess.run([sys.executable, '-B', str(self.root / 'openwrite.py'), *args],
                              cwd=self.root, capture_output=True, text=True)

    def test_dimensions_resolve_independently_and_accept_custom_descriptions(self):
        before = self.config.read_bytes()
        self.assertEqual(preferences.cover_style(self.root), STYLE)
        custom = preferences.cover_style(self.root, visual_style='自定义纸雕质感', color_tone='品牌色 #12AABB')
        self.assertEqual(custom, dict(STYLE, visual_style='自定义纸雕质感', color_tone='品牌色 #12AABB'))
        self.assertEqual(self.config.read_bytes(), before)

    def test_style_field_selects_preset_and_cli_override(self):
        self.config.write_text('wechat:\n  accounts:\n    主号:\n      cover:\n'
                               '        style: full-bleed-single-title\n'
                               '        color_tone: 暖黄奶油色\n', encoding='utf-8')
        style = preferences.cover_style(self.root)
        self.assertEqual(style['style'], 'full-bleed-single-title')
        self.assertEqual(style['color_tone'], '暖黄奶油色')
        result = self.cli('new', 'single', '--cover-style', 'left-text-right-image')
        self.assertEqual(result.returncode, 0, result.stderr)
        state = workflow.load(self.root / 'articles/single')
        self.assertEqual(state['cover_style']['style'], 'left-text-right-image')

    def test_new_and_init_persist_snapshot_and_prompt_overrides_only_one_dimension(self):
        result = self.cli('new', 'topic', '--cover-visual-style', '科技线稿')
        self.assertEqual(result.returncode, 0, result.stderr)
        article = self.root / 'articles/topic'
        state = workflow.load(article)
        self.assertEqual(state['cover_style'], dict(STYLE, visual_style='科技线稿'))
        before = (layout.path(article, 'workflow.json')).read_bytes()
        self.config.write_text('wechat:\n  accounts:\n    主号:\n      cover:\n'
                               '        color_tone: 青绿渐变\n', encoding='utf-8')
        result = self.cli('workflow', 'status', str(article))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('暖黄奶油色', result.stdout)
        self.assertEqual((layout.path(article, 'workflow.json')).read_bytes(), before)
        existing = self.root / 'existing'
        existing.mkdir()
        result = self.cli('workflow', 'init', str(existing), '--cover-layout', '居中标题')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(workflow.load(existing)['cover_style'], {'layout': '居中标题', 'color_tone': '青绿渐变'})

    def test_style_can_be_changed_before_cover_without_reading_new_defaults(self):
        self.assertEqual(self.cli('new', 'topic').returncode, 0)
        article = self.root / 'articles/topic'
        self.config.write_text('wechat:\n  accounts:\n    主号:\n      cover:\n'
                               '        layout: 居中标题\n', encoding='utf-8')
        result = self.cli('workflow', 'cover-style', str(article), '--cover-color-tone', '青绿渐变')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(workflow.load(article)['cover_style'], dict(STYLE, color_tone='青绿渐变'))

    def test_completed_cover_requires_reset_before_style_changes(self):
        self.assertEqual(self.cli('new', 'topic').returncode, 0)
        article = self.root / 'articles/topic'
        state = workflow.load(article)
        # The command rejects by stage without touching or claiming verification of artifacts.
        state['completed'] = [{'step': step, 'proof': 'fixture'} for step in workflow.STEPS[:4]]
        workflow.write_json(layout.path(article, 'workflow.json'), state)
        before = (layout.path(article, 'workflow.json')).read_bytes()
        result = self.cli('workflow', 'cover-style', str(article), '--cover-layout', '居中标题')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--from cover', result.stderr)
        self.assertEqual((layout.path(article, 'workflow.json')).read_bytes(), before)

    def test_bad_descriptions_are_rejected_before_creating_task(self):
        result = self.cli('new', 'bad', '--cover-layout', 'a\nb')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'articles/bad').exists())

    def test_wechat_cover_settings_do_not_apply_to_rednote(self):
        result = self.cli('new', 'rednote', '--platform', 'rednote')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('cover_style', workflow.load(self.root / 'articles/rednote'))
        result = self.cli('new', 'wrong', '--platform', 'rednote', '--cover-layout', '左文右图')
        self.assertNotEqual(result.returncode, 0)

    def test_effective_request_and_overlay_stay_in_left_region(self):
        article = self.root / 'article'
        article.mkdir()
        title = '不用复杂操作也能看懂这个工具'
        workflow.initialize(article, title, outline_approval=False, cover_style=STYLE)
        base = self.root / 'base.png'
        image = Image.new('RGB', (1024, 432), '#FFF3D2')
        ImageDraw.Draw(image).rectangle((620, 30, 1000, 400), fill='#DA9350')
        image.save(base)
        raw = {'id': 'cover', 'role': 'cover', 'output': 'cover.png', 'width': 1024,
               'height': 432, 'prompt': '主题插画', 'text': [],
               'overlay': {'title': title, 'subtitle': '关键词与价值说明', 'color': '#3D2C22'}}
        workflow.write_json(layout.path(article, 'image-requests.json'), {'version': 1, 'images': [raw]})
        runtime = workflow.image_runtime()
        resolved = runtime.load_request(article, 'cover')
        self.assertEqual(resolved['style'], STYLE['visual_style'])
        self.assertEqual(resolved['palette'], [STYLE['color_tone']])
        self.assertIn('smooth continuous warm gradient', resolved['composition'])
        self.assertIn('right ~50%', resolved['composition'])
        self.assertEqual(resolved['overlay']['position'], 'center-left')
        self.assertEqual(resolved['overlay']['text_width_ratio'], 0.45)
        try:
            runtime.load_module('cover_font_test', 'cover_text.py').resolve_font({})
        except ValueError:
            self.skipTest('本机缺少可用中文字体')
        result = runtime.produce(Namespace(article=str(article), id='cover', backend='file', source=str(base),
                                           profile=None, timeout=10, fit='exact', overwrite=False))
        effective = workflow.requests(article)[0]
        self.assertEqual(result['request_hash'], runtime.request_hash(effective))
        workflow.image_proof(article, effective)
        with Image.open(article / 'cover.png') as picture:
            self.assertIsNone(ImageChops.difference(picture.crop((600, 0, 1024, 432)),
                                                   image.crop((600, 0, 1024, 432))).getbbox())
            self.assertIsNotNone(ImageChops.difference(picture.crop((0, 0, 550, 432)),
                                                      image.crop((0, 0, 550, 432))).getbbox())

    def test_three_level_text_hierarchy(self):
        runtime = workflow.image_runtime()
        try:
            cover_text = runtime.load_module('cover_text_levels', 'cover_text.py')
            cover_text.resolve_font({})
        except ValueError:
            self.skipTest('本机缺少可用中文字体')
        overlay = {'title': 'AI 杀不死剪映', 'subtitle': '一年赚走近百亿',
                   'tagline': '真正危险的是别人', 'color': '#3D2C22',
                   'position': 'center-left', 'scrim': False}
        layout_box = cover_text._layout(overlay, 1024, 432)
        self.assertTrue(layout_box['tag_lines'])
        self.assertLess(layout_box['tag_font'].size, layout_box['sub_font'].size)
        self.assertLess(layout_box['sub_font'].size, layout_box['title_font'].size)
        base = self.root / 'levels-base.png'
        Image.new('RGB', (1024, 432), '#FFF3D2').save(base)
        out = self.root / 'levels-out.png'
        cover_text.render(base, out, overlay, 1024, 432)
        with Image.open(out) as picture:
            self.assertEqual(picture.size, (1024, 432))
            self.assertIsNotNone(ImageChops.difference(picture, Image.open(base)).getbbox())

    def test_single_title_style_uses_full_cover_and_centers_text(self):
        article = self.root / 'single-title'
        article.mkdir()
        workflow.initialize(article, '单标题封面', outline_approval=False,
                            cover_style={'style': 'full-bleed-single-title', 'color_tone': '暖黄奶油色'})
        raw = {'id': 'cover', 'role': 'cover', 'output': 'cover.png', 'width': 1024,
               'height': 432, 'prompt': '主题插画', 'text': [],
               'overlay': {'title': '单行大标题', 'subtitle': '单标题样式不渲染副题',
                           'color': '#3D2C22'}}
        manifest = layout.path(article, 'image-requests.json')
        workflow.write_json(manifest, {'version': 1, 'images': [raw]})
        runtime = workflow.image_runtime()
        resolved = runtime.load_request(article, 'cover')
        self.assertEqual(resolved['overlay']['position'], 'center')
        self.assertEqual(resolved['overlay']['text_width_ratio'], 0.8)
        self.assertNotIn('subtitle', resolved['overlay'])
        self.assertIn('the full ~100%', resolved['composition'])
        self.assertIn('the full ~80%', resolved['composition'])
        self.assertNotIn('the right ~50%', resolved['composition'])

        # 样式限定居中方位：左侧方位回落到默认 center，居中方位保持用户选择。
        workflow.write_json(manifest, {'version': 1, 'images': [dict(raw, overlay=dict(raw['overlay'],
                                                                                          position='bottom-left'))]})
        self.assertEqual(runtime.load_request(article, 'cover')['overlay']['position'], 'center')
        workflow.write_json(manifest, {'version': 1, 'images': [dict(raw, overlay=dict(raw['overlay'],
                                                                                          position='bottom-center'))]})
        self.assertEqual(runtime.load_request(article, 'cover')['overlay']['position'], 'bottom-center')

        try:
            cover_text = runtime.load_module('cover_text_centered', 'cover_text.py')
            cover_text.resolve_font({})
        except ValueError:
            self.skipTest('本机缺少可用中文字体')
        overlay = runtime.load_request(article, 'cover')['overlay']
        overlay['position'] = 'center'
        width, height = 1024, 432
        base = self.root / 'centered-base.png'
        Image.new('RGB', (width, height), '#FFF3D2').save(base)

        def text_box(name: str, title: str):
            out = self.root / name
            cover_text.render(base, out, dict(overlay, title=title), width, height)
            with Image.open(base) as background, Image.open(out) as picture:
                box = ImageChops.difference(picture.convert('RGB'),
                                            background.convert('RGB')).getbbox()
            self.assertIsNotNone(box)
            return box

        for name, title in (('centered-single.png', '单行大标题'),
                            ('centered-wrapped.png', '单标题样式的长标题换行之后依然整行水平居中')):
            box = text_box(name, title)
            self.assertLessEqual(abs((box[0] + box[2]) / 2 - width / 2), 8)

    def test_legacy_request_fingerprint_is_unchanged_without_style_snapshot(self):
        article = self.root / 'old'
        article.mkdir()
        workflow.initialize(article, '旧文章')
        raw = {'id': 'cover', 'role': 'cover', 'output': 'cover.png', 'width': 1024,
               'height': 432, 'prompt': '旧图需求', 'text': []}
        workflow.write_json(layout.path(article, 'image-requests.json'), {'version': 1, 'images': [raw]})
        runtime = workflow.image_runtime()
        self.assertEqual(runtime.load_request(article, 'cover'), raw)


if __name__ == '__main__':
    unittest.main()
