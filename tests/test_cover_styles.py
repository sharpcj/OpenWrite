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
        self.config = self.root / '.env'
        self.config.write_text('WeChat=true\nWriterRole=SelfMediaBlogger\n'
                               'WeChatCoverLayout="左文右图"\n'
                               'WeChatCoverVisualStyle="温暖插画"\n'
                               'WeChatCoverColorTone="暖黄奶油色"\n')

    def cli(self, *args):
        for name in ('openwrite.py', 'workflow.py', 'preferences.py', 'platforms.py', 'layout.py'):
            shutil.copy2(ROOT / name, self.root / name)
        return subprocess.run([sys.executable, '-B', str(self.root / 'openwrite.py'), *args],
                              cwd=self.root, capture_output=True, text=True)

    def test_dimensions_resolve_independently_and_accept_custom_descriptions(self):
        before = self.config.read_bytes()
        self.assertEqual(preferences.cover_style(self.root), STYLE)
        custom = preferences.cover_style(self.root, visual_style='自定义纸雕质感', color_tone='品牌色 #12AABB')
        self.assertEqual(custom, dict(STYLE, visual_style='自定义纸雕质感', color_tone='品牌色 #12AABB'))
        self.assertEqual(self.config.read_bytes(), before)

    def test_new_and_init_persist_snapshot_and_prompt_overrides_only_one_dimension(self):
        result = self.cli('new', 'topic', '--cover-visual-style', '科技线稿')
        self.assertEqual(result.returncode, 0, result.stderr)
        article = self.root / 'articles/topic'
        state = workflow.load(article)
        self.assertEqual(state['cover_style'], dict(STYLE, visual_style='科技线稿'))
        before = (layout.path(article, 'workflow.json')).read_bytes()
        self.config.write_text('WeChat=true\nWeChatCoverColorTone="青绿渐变"\n')
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
        self.config.write_text('WeChat=true\nWeChatCoverLayout="居中标题"\n')
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
        self.assertIn('right 45%', resolved['composition'])
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
