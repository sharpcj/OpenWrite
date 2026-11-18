"""Multi-source image capability: config, auto fallback, online/stock backends, cover overlay."""
import layout
from argparse import Namespace
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image
from workflow_fixtures import seed_body

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(
        f'test_{name}', ROOT / 'skills/openwrite-images/scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime = load_script('produce')
config = runtime.image_config


def png_bytes(size=(120, 80), color='green'):
    buffer = io.BytesIO()
    Image.new('RGB', size, color).save(buffer, format='PNG')
    return buffer.getvalue()


class ImageConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-imgcfg-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write_sources(self, **fields):
        lines = ['image_sources:'] + [f'  {key}: "{value}"' for key, value in fields.items()]
        (self.root / 'openwrite.yaml').write_text('\n'.join(lines) + '\n', encoding='utf-8')

    def test_config_values_and_environment_precedence(self):
        self.write_sources(fal_key='from-config-file', comfyui_server_url='http://localhost:6677')
        self.assertEqual(config.setting('FAL_KEY', root=self.root), 'from-config-file')
        with patch.dict(os.environ, {'FAL_KEY': 'from-process'}):
            self.assertEqual(config.setting('FAL_KEY', root=self.root), 'from-process')

    def test_comfyui_urls_local_first_and_dedup(self):
        self.write_sources(comfyui_server_url='http://10.0.0.5:8188, http://localhost:6677 ,http://10.0.0.5:8188')
        self.assertEqual(config.comfyui_urls(self.root),
                         ['http://localhost:6677', 'http://10.0.0.5:8188'])

    def test_comfyui_urls_default_and_legacy(self):
        self.assertEqual(config.comfyui_urls(self.root), ['http://localhost:8188'])
        with patch.object(config, 'skill_config', return_value={'comfyui_url': 'http://localhost:9999'}):
            self.assertEqual(config.comfyui_urls(self.root), ['http://localhost:9999'])

    def test_invalid_comfyui_url_rejected(self):
        self.write_sources(comfyui_server_url='localhost:6677')
        with self.assertRaises(ValueError):
            config.comfyui_urls(self.root)

    def test_backend_key_aliases(self):
        self.write_sources(fal_ai_api_key='alias-key')
        self.assertEqual(config.backend_key('fal', self.root), 'alias-key')
        self.assertEqual(config.backend_key('pexels', self.root), '')

    def test_source_priority_defaults_and_override(self):
        self.assertEqual(config.source_priority('cover')[0], 'comfyui')
        self.assertEqual(config.source_priority('content')[0], 'file')
        with patch.object(config, 'skill_config',
                          return_value={'source_priority': {'cover': ['file', 'comfyui']}}):
            self.assertEqual(config.source_priority('cover'), ['file', 'comfyui'])


class AutoFallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-auto-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.article = self.root / 'article'
        self.article.mkdir()
        self.source = self.root / 'source.png'
        Image.new('RGB', (60, 40), 'red').save(self.source)
        self.request = {'id': 'cover', 'role': 'cover', 'output': 'cover.png',
                        'width': 60, 'height': 40, 'prompt': '测试封面', 'text': []}
        self.write_plan([self.request])

    def write_plan(self, images):
        (layout.path(self.article, 'image-requests.json')).write_text(
            json.dumps({'version': 1, 'images': images}, ensure_ascii=False), encoding='utf-8')

    def args(self, **overrides):
        values = dict(article=str(self.article), id='cover', backend='auto',
                      source=None, profile=None, timeout=10, fit=None, overwrite=False)
        values.update(overrides)
        return Namespace(**values)

    def fake_backend(self, failures, size=(60, 40)):
        def obtain(backend, args, request, staging):
            if backend in failures:
                error = failures[backend]
                if isinstance(error, SystemExit):
                    raise error
                raise ValueError(error)
            raw = staging / f'{backend}.png'
            Image.new('RGB', size, 'blue').save(raw)
            return raw, {'model': backend}
        return obtain

    def test_auto_falls_back_from_comfyui_to_fal(self):
        self.request['preferred_sources'] = ['comfyui', 'fal']
        self.write_plan([self.request])
        with patch.object(config, 'backend_key', return_value='key'), \
             patch.object(runtime, 'obtain_backend',
                          side_effect=self.fake_backend({'comfyui': 'ComfyUI 离线'})):
            result = runtime.produce(self.args())
        self.assertEqual(result['backend'], 'fal')
        self.assertEqual(result['fit'], 'exact')
        self.assertEqual(result['attempts'], [{'backend': 'comfyui', 'error': 'ComfyUI 离线'}])
        self.assertTrue((self.article / 'cover.png').is_file())

    def test_auto_survives_comfyui_system_exit(self):
        self.request['preferred_sources'] = ['comfyui', 'fal']
        self.write_plan([self.request])
        with patch.object(config, 'backend_key', return_value='key'), \
             patch.object(runtime, 'obtain_backend',
                          side_effect=self.fake_backend({'comfyui': SystemExit(1)})):
            result = runtime.produce(self.args())
        self.assertEqual(result['backend'], 'fal')

    def test_auto_stock_uses_cover_fit_by_default(self):
        self.request['preferred_sources'] = ['pexels']
        self.request['keywords'] = ['office']
        self.write_plan([self.request])
        with patch.object(config, 'backend_key', return_value='key'), \
             patch.object(runtime, 'obtain_backend', side_effect=self.fake_backend({}, size=(120, 80))):
            result = runtime.produce(self.args())
        self.assertEqual(result['backend'], 'pexels')
        self.assertEqual(result['fit'], 'cover')
        with Image.open(self.article / 'cover.png') as picture:
            self.assertEqual(picture.size, (60, 40))

    def test_explicit_fit_overrides_auto_default(self):
        self.request['preferred_sources'] = ['pexels']
        self.request['keywords'] = ['office']
        self.write_plan([self.request])
        with patch.object(config, 'backend_key', return_value='key'), \
             patch.object(runtime, 'obtain_backend', side_effect=self.fake_backend({}, size=(120, 80))):
            result = runtime.produce(self.args(fit='contain'))
        self.assertEqual(result['fit'], 'contain')

    def test_unconfigured_sources_are_skipped(self):
        with patch.object(config, 'backend_key', return_value=''), \
             patch.object(runtime, 'obtain_backend',
                          side_effect=self.fake_backend({'comfyui': '离线'})) as obtain:
            with self.assertRaises(ValueError) as caught:
                runtime.produce(self.args())
        self.assertIn('所有图片来源均失败', str(caught.exception))
        self.assertEqual(obtain.call_count, 1)
        self.assertEqual(obtain.call_args.args[0], 'comfyui')

    def test_no_available_source_reports_configuration(self):
        with patch.object(runtime, 'backend_available', return_value=False):
            with self.assertRaises(ValueError) as caught:
                runtime.produce(self.args())
        self.assertIn('没有可用的图片来源', str(caught.exception))
        self.assertFalse((self.article / 'cover.png').exists())

    def test_auto_file_uses_request_source_file(self):
        self.request['role'] = 'content'
        self.request['source_file'] = str(self.source)
        self.request['source_url'] = 'https://docs.example.com/figure.png'
        self.request['attribution'] = 'Example Official Docs'
        self.write_plan([self.request])
        result = runtime.produce(self.args(id='cover'))
        self.assertEqual(result['backend'], 'file')
        self.assertEqual(result['source_url'], 'https://docs.example.com/figure.png')
        self.assertEqual(result['attribution'], 'Example Official Docs')

    def test_stock_requires_keywords(self):
        self.request['preferred_sources'] = ['pexels']
        self.write_plan([self.request])
        with patch.object(config, 'backend_key', return_value='key'):
            with self.assertRaises(ValueError) as caught:
                runtime.produce(self.args())
        self.assertIn('keywords', str(caught.exception))


class RequestValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-validate-')
        self.addCleanup(self.tmp.cleanup)
        self.article = Path(self.tmp.name)
        self.base = {'id': 'cover', 'role': 'cover', 'output': 'cover.png',
                     'width': 60, 'height': 40, 'prompt': '测试', 'text': []}

    def write(self, item):
        (layout.path(self.article, 'image-requests.json')).write_text(
            json.dumps({'version': 1, 'images': [item]}, ensure_ascii=False), encoding='utf-8')

    def test_invalid_new_fields_rejected(self):
        cases = [
            dict(self.base, preferred_sources=['unknown']),
            dict(self.base, preferred_sources=['comfyui', 'comfyui']),
            dict(self.base, preferred_sources=[]),
            dict(self.base, keywords='not-a-list'),
            dict(self.base, keywords=['']),
            dict(self.base, source_file=3),
            dict(self.base, overlay={'subtitle': '只有副标题'}),
            dict(self.base, overlay={'title': '标题'}, text=['画面文字']),
            dict(self.base, overlay={'title': '标题', 'position': 'middle'}),
            dict(self.base, overlay={'title': '标题', 'font_size': 'big'}),
            dict(self.base, role='content', overlay={'title': '标题'}),
            dict(self.base, card={'title': '卡片'}, overlay={'title': '标题'}),
        ]
        for case in cases:
            with self.subTest(case=case):
                self.write(case)
                with self.assertRaises(ValueError):
                    runtime.load_request(self.article, 'cover')

    def test_valid_new_fields_accepted(self):
        self.write(dict(self.base, preferred_sources=['file', 'comfyui'],
                        keywords=['检索增强'], overlay={'title': '标题', 'subtitle': '副标题'}))
        item = runtime.load_request(self.article, 'cover')
        self.assertEqual(item['overlay']['title'], '标题')


class OnlineBackendTests(unittest.TestCase):
    def setUp(self):
        self.module = load_script('image_sources')
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-online-')
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name) / 'raw.png'

    def test_hunyuan_size_scaling(self):
        self.assertEqual(self.module._hunyuan_size(60, 40, 'hy-image-v3.5-preview'), '384x256')
        self.assertEqual(self.module._hunyuan_size(1024, 432, 'hy-image-v3.5-preview'), '1024x432')
        scaled = self.module._hunyuan_size(8192, 8192, 'hy-image-v3.5-preview')
        w, h = (int(v) for v in scaled.split('x'))
        self.assertLessEqual(w * h, 16777216)

    def test_hunyuan_payload_and_bearer_auth(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {'choices': [{'delta': {'image': {'url': 'https://cos/result.png'}}}]}
        with patch.object(self.module.image_config, 'backend_key', return_value='tk-key'), \
             patch.object(self.module.requests, 'post', return_value=response) as post, \
             patch.object(self.module, '_download', return_value=self.output) as download:
            meta = self.module.generate_hunyuan('画一只猫', self.output, 1024, 432, 60)
        args, kwargs = post.call_args
        self.assertEqual(args[0], self.module.HUNYUAN_V35_URL)
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer tk-key')
        self.assertEqual(kwargs['json']['model'], 'hy-image-v3.5-preview')
        self.assertEqual(kwargs['json']['size'], '1024x432')
        self.assertEqual(kwargs['json']['messages'][0]['content'][0]['text'], '画一只猫')
        self.assertEqual(meta['source_url'], 'https://cos/result.png')
        download.assert_called_once()

    def test_hunyuan_error_frame_reported(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {'choices': [{'delta': {}, 'finish_reason': 'error'}],
                                      'error': {'code': 'content_filter', 'message': 'rejected'}}
        with patch.object(self.module.image_config, 'backend_key', return_value='tk-key'), \
             patch.object(self.module.requests, 'post', return_value=response):
            with self.assertRaises(ValueError) as caught:
                self.module.generate_hunyuan('提示词', self.output, 1024, 432, 60)
        self.assertIn('content_filter', str(caught.exception))

    def test_fal_queue_flow(self):
        submit = MagicMock(status_code=200)
        submit.json.return_value = {'status_url': 'https://queue/status', 'response_url': 'https://queue/result',
                                    'request_id': 'req-1'}
        status = MagicMock()
        status.json.return_value = {'status': 'COMPLETED'}
        result = MagicMock()
        result.json.return_value = {'images': [{'url': 'https://fal-cdn/image.png'}]}
        with patch.object(self.module.image_config, 'backend_key', return_value='fal-key'), \
             patch.object(self.module.requests, 'post', return_value=submit) as post, \
             patch.object(self.module.requests, 'get', side_effect=[status, result]), \
             patch.object(self.module, '_download', return_value=self.output):
            meta = self.module.generate_fal('a cat', self.output, 100, 100, 60)
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['image_size'], {'width': 96, 'height': 96})
        self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'Key fal-key')
        self.assertEqual(meta['source_url'], 'https://fal-cdn/image.png')

    def test_missing_key_blocks_paid_call(self):
        with patch.object(self.module.image_config, 'backend_key', return_value=''), \
             patch.object(self.module.requests, 'post') as post:
            with self.assertRaises(ValueError) as caught:
                self.module.generate_hunyuan('提示词', self.output, 1024, 432, 60)
        post.assert_not_called()
        self.assertIn('TENCENT_TOKENHUB_API_KEY', str(caught.exception))


class StockBackendTests(unittest.TestCase):
    def setUp(self):
        self.module = load_script('image_sources')
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-stock-')
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name) / 'raw.png'

    def search_response(self, payload):
        response = MagicMock(status_code=200)
        response.json.return_value = payload
        return response

    def download_response(self):
        response = MagicMock(status_code=200)
        response.__enter__.return_value = response
        response.iter_content.return_value = [png_bytes()]
        return response

    def test_pexels_search_download_and_attribution(self):
        search = self.search_response({'photos': [
            {'id': 1, 'width': 1200, 'height': 800, 'url': 'https://pexels.com/photo/1',
             'photographer': 'Alice', 'src': {'large2x': 'https://images.pexels.com/1.jpeg'}},
        ]})
        with patch.object(self.module.image_config, 'backend_key', return_value='px-key'), \
             patch.object(self.module.requests, 'get', side_effect=[search, self.download_response()]) as get:
            meta = self.module.fetch_stock('pexels', ['office', 'desk'], self.output, 1024, 768, 60)
        self.assertEqual(get.call_args_list[0].args[0], 'https://api.pexels.com/v1/search')
        self.assertEqual(get.call_args_list[0].kwargs['headers']['Authorization'], 'px-key')
        self.assertTrue(self.output.is_file())
        self.assertEqual(meta['source_url'], 'https://pexels.com/photo/1')
        self.assertIn('Alice', meta['attribution'])
        self.assertIn('Pexels', meta['attribution'])

    def test_unsplash_triggers_download_tracking(self):
        search = self.search_response({'results': [
            {'id': 'x', 'width': 1600, 'height': 900,
             'urls': {'regular': 'https://images.unsplash.com/x'},
             'links': {'html': 'https://unsplash.com/photos/x',
                       'download_location': 'https://api.unsplash.com/photos/x/download'},
             'user': {'name': 'Bob'}},
        ]})
        tracking = MagicMock(status_code=200)
        with patch.object(self.module.image_config, 'backend_key', return_value='un-key'), \
             patch.object(self.module.requests, 'get',
                          side_effect=[search, tracking, self.download_response()]) as get:
            meta = self.module.fetch_stock('unsplash', ['mountain'], self.output, 1024, 768, 60)
        self.assertEqual(get.call_args_list[1].args[0], 'https://api.unsplash.com/photos/x/download')
        self.assertIn('Bob', meta['attribution'])

    def test_candidate_selection_prefers_resolution_and_ratio(self):
        candidates = [
            {'download': 'a', 'width': 400, 'height': 300},
            {'download': 'b', 'width': 2000, 'height': 1500},
            {'download': 'c', 'width': 2000, 'height': 2000},
        ]
        chosen = self.module._pick_candidate(candidates, 1024, 768)
        self.assertEqual(chosen['download'], 'b')

    def test_empty_results_reported(self):
        with patch.object(self.module.image_config, 'backend_key', return_value='key'), \
             patch.object(self.module.requests, 'get', return_value=self.search_response({'photos': []})):
            with self.assertRaises(ValueError):
                self.module.fetch_stock('pexels', ['nothing'], self.output, 1024, 768, 60)


class CoverOverlayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-overlay-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.article = self.root / 'article'
        self.article.mkdir()
        self.base = self.root / 'base.png'
        Image.new('RGB', (200, 100), '#1a1f5c').save(self.base)
        self.cover_text = load_script('cover_text')
        try:
            self.cover_text.resolve_font({})
        except ValueError:
            self.skipTest('本机没有可用中文字体')

    def write_plan(self, overlay):
        request = {'id': 'cover', 'role': 'cover', 'output': 'cover.png',
                   'width': 200, 'height': 100, 'prompt': '底图', 'text': [], 'overlay': overlay}
        (layout.path(self.article, 'image-requests.json')).write_text(
            json.dumps({'version': 1, 'images': [request]}, ensure_ascii=False), encoding='utf-8')
        return request

    def args(self, overwrite=False):
        return Namespace(article=str(self.article), id='cover', backend='file',
                         source=str(self.base), profile=None, timeout=10,
                         fit='exact', overwrite=overwrite)

    def test_overlay_typesets_title_and_subtitle(self):
        self.write_plan({'title': '封面标题', 'subtitle': '副标题文案'})
        result = runtime.produce(self.args())
        self.assertEqual(result['status'], 'ready')
        with Image.open(self.article / 'cover.png') as picture:
            self.assertEqual(picture.size, (200, 100))
            self.assertEqual(picture.format, 'PNG')
        self.assertNotEqual((self.article / 'cover.png').read_bytes(), self.base.read_bytes())

    def test_overlay_positions_and_scrim_options(self):
        for position in ('top-center', 'center', 'bottom-right'):
            with self.subTest(position=position):
                self.write_plan({'title': '标题', 'position': position, 'scrim': False})
                runtime.produce(self.args(overwrite=True))
                with Image.open(self.article / 'cover.png') as picture:
                    self.assertEqual(picture.size, (200, 100))

    def test_overlong_title_fails_without_artifact(self):
        self.write_plan({'title': '这是一个超长的标题' * 6})
        with self.assertRaises(ValueError):
            runtime.produce(self.args())
        self.assertFalse((self.article / 'cover.png').exists())

    def test_cover_title_independent_of_article_title(self):
        import workflow
        seed_body(self.article)
        # 封面大标题可短于文章标题（营销标题），不再强制一致。
        request = {'id': 'cover', 'role': 'cover', 'output': 'cover.png',
                   'width': 200, 'height': 100, 'prompt': '底图', 'text': [],
                   'overlay': {'title': '别的标题', 'subtitle': '信息副题', 'tagline': '弱化小标语'}}
        (layout.path(self.article, 'image-requests.json')).write_text(
            json.dumps({'version': 1, 'images': [request]}, ensure_ascii=False), encoding='utf-8')
        runtime.produce(self.args())
        state = workflow.complete(self.article, 'cover', reviewed=True, note='已检查封面叠字')
        self.assertEqual(state['completed'][-1]['step'], 'cover')


    def test_text_levels_are_theme_defined(self):
        import workflow
        # 仅大标题主题：即使提供副标题/标语，也只保留大标题。
        workflow.initialize(self.article, '测试文章',
                            cover_style={'layout': '左文单标题', 'visual_style': '温暖插画',
                                         'color_tone': '暖黄奶油色'})
        self.write_plan({'title': '大标题', 'subtitle': '副标题', 'tagline': '小标语'})
        resolved = runtime.load_request(self.article, 'cover')
        self.assertEqual(resolved['overlay']['title'], '大标题')
        self.assertNotIn('subtitle', resolved['overlay'])
        self.assertNotIn('tagline', resolved['overlay'])
        # 三级主题：保留副标题与标语。
        state = workflow.load(self.article)
        state['cover_style']['layout'] = '左文右图'
        workflow.write_json(layout.path(self.article, 'workflow.json'), state)
        resolved = runtime.load_request(self.article, 'cover')
        self.assertEqual(resolved['overlay']['subtitle'], '副标题')
        self.assertEqual(resolved['overlay']['tagline'], '小标语')


if __name__ == '__main__':
    unittest.main()
