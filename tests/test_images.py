"""Exercise image contracts with real local images and mocked external backends."""
import layout
from argparse import Namespace
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from workflow_fixtures import seed_body

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('image_runtime', ROOT / 'skills/openwrite-images/scripts/produce.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class ImageCapabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-image-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.article = self.root / 'article with spaces'
        self.article.mkdir()
        self.source = self.root / 'source.jpg'
        Image.new('RGB', (60, 40), 'red').save(self.source)
        self.request = {
            'id': 'cover', 'role': 'cover', 'output': 'cover.png',
            'width': 60, 'height': 40, 'prompt': '知识卡片与光线',
            'text': ['文章标题'], 'palette': ['red'], 'composition': '留白',
        }
        self.write_plan([self.request])

    def write_plan(self, images):
        (layout.path(self.article, 'image-requests.json')).write_text(
            json.dumps({'version': 1, 'images': images}, ensure_ascii=False), encoding='utf-8',
        )

    def args(self, **overrides):
        values = dict(article=str(self.article), id='cover', backend='file',
                      source=str(self.source), profile=None, timeout=10,
                      fit='exact', overwrite=False)
        values.update(overrides)
        return Namespace(**values)

    def test_import_decodes_and_converts_jpeg_to_real_png(self):
        result = runtime.produce(self.args())
        with Image.open(self.article / 'cover.png') as picture:
            self.assertEqual(picture.format, 'PNG')
            self.assertEqual(picture.size, (60, 40))
        self.assertEqual(result['review'], 'pending')
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['request_hash'], runtime.request_hash(self.request))
        report = json.loads((layout.path(self.article, 'image-results.json')).read_text())
        self.assertEqual(report['images'], [result])

    def test_dimension_mismatch_does_not_create_success_artifacts(self):
        self.request['width'] = 80
        self.write_plan([self.request])
        with self.assertRaises(ValueError):
            runtime.produce(self.args())
        self.assertFalse((self.article / 'cover.png').exists())
        self.assertFalse((layout.path(self.article, 'image-results.json')).exists())

    def test_explicit_contain_adds_padding_at_target_size(self):
        self.request['height'] = 60
        self.write_plan([self.request])
        runtime.produce(self.args(fit='contain'))
        with Image.open(self.article / 'cover.png') as picture:
            self.assertEqual(picture.size, (60, 60))
            self.assertEqual(picture.getpixel((0, 0)), (255, 255, 255))

    def test_invalid_image_is_not_treated_as_an_artifact(self):
        self.source.write_text('not an image')
        with self.assertRaises(OSError):
            runtime.produce(self.args())
        self.assertFalse((layout.path(self.article, 'image-results.json')).exists())

    def test_existing_artifacts_survive_a_failed_replacement(self):
        runtime.produce(self.args())
        old_image = (self.article / 'cover.png').read_bytes()
        old_report = (layout.path(self.article, 'image-results.json')).read_bytes()
        self.source.write_text('broken')
        with self.assertRaises(OSError):
            runtime.produce(self.args(overwrite=True))
        self.assertEqual((self.article / 'cover.png').read_bytes(), old_image)
        self.assertEqual((layout.path(self.article, 'image-results.json')).read_bytes(), old_report)
        with patch.object(runtime, 'obtain_source') as obtain:
            with self.assertRaises(ValueError):
                runtime.produce(self.args())
            obtain.assert_not_called()

    def test_invalid_requests_are_rejected_before_backend_calls(self):
        for bad in [dict(self.request, output='../cover.png'),
                    dict(self.request, width=True),
                    dict(self.request, text='not a list'),
                    dict(self.request, palette='not a list')]:
            with self.subTest(bad=bad), patch.object(runtime, 'obtain_source') as obtain:
                self.write_plan([bad])
                with self.assertRaises(ValueError):
                    runtime.produce(self.args(backend='comfyui', source=None))
                obtain.assert_not_called()
        self.write_plan([self.request, dict(self.request)])
        with self.assertRaises(ValueError):
            runtime.load_request(self.article, 'cover')

    def test_corrupt_previous_report_blocks_backend_call(self):
        (layout.path(self.article, 'image-results.json')).write_text('{invalid')
        with patch.object(runtime, 'obtain_source') as obtain:
            with self.assertRaises(ValueError):
                runtime.produce(self.args(backend='comfyui', source=None))
            obtain.assert_not_called()

    def test_comfy_request_uses_shared_workflow_and_imports_real_output(self):
        comfy = runtime.load_module('shared_comfy_test', 'comfyui_gen.py')
        Image.new('RGB', (60, 40), 'blue').save(self.root / 'comfy.png')
        history = {'outputs': {'save': {'images': [{'filename': 'comfy.png'}]}}}
        with patch.object(runtime, 'load_module', return_value=comfy), \
             patch.object(comfy, 'OUTPUT_DIR', str(self.root)), \
             patch.object(comfy, 'submit_prompt', return_value='task') as submit, \
             patch.object(comfy, 'wait_for_result', return_value=history):
            result = runtime.produce(self.args(backend='comfyui', source=None))
        workflow = submit.call_args.args[0]
        positives, negatives, found = comfy._find_prompt_node_ids(workflow)
        self.assertTrue(found)
        self.assertTrue(positives)
        self.assertTrue(all('文章标题' in workflow[node]['inputs']['text'] for node in positives))
        latent = [node['inputs'] for node in workflow.values()
                  if node.get('class_type') in comfy.EMPTY_LATENT_CLASSES]
        self.assertTrue(all((node['width'], node['height']) == (60, 40) for node in latent))
        self.assertEqual(result['backend'], 'comfyui')
        self.assertTrue((self.article / 'cover.png').is_file())

    def test_root_cli_imports_relative_file_from_another_directory(self):
        seed_body(self.article)
        result = subprocess.run(
            [sys.executable, '-B', str(ROOT / 'openwrite.py'), 'image',
             str(self.article), '--id', 'cover', '--backend', 'file', '--source', 'source.jpg'],
            cwd=self.root, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['output'], 'cover.png')

    def test_new_request_fingerprint_changes_with_visual_requirements(self):
        self.assertNotEqual(runtime.request_hash(self.request),
                            runtime.request_hash(dict(self.request, composition='改为居中')))

    def test_model_selection_uses_rendered_text_not_chinese_composition(self):
        self.request['text'] = ['Hello']
        self.write_plan([self.request])
        comfy = runtime.load_module('text_selection_test', 'comfyui_gen.py')
        Image.new('RGB', (60, 40), 'blue').save(self.root / 'comfy.png')
        history = {'outputs': {'save': {'images': [{'filename': 'comfy.png'}]}}}
        with patch.object(runtime, 'load_module', return_value=comfy), \
             patch.object(comfy, 'DEFAULT_PROFILE', 'auto'), \
             patch.object(comfy, 'OUTPUT_DIR', str(self.root)), \
             patch.object(comfy, 'submit_prompt', return_value='task'), \
             patch.object(comfy, 'wait_for_result', return_value=history), \
             patch.object(comfy, 'resolve_workflow_path', wraps=comfy.resolve_workflow_path) as resolve:
            runtime.produce(self.args(backend='comfyui', source=None))
        self.assertEqual(resolve.call_args.args[1], comfy.AUTO_RULES['fallback'])

    def test_comfy_execution_error_is_reported_without_waiting_for_timeout(self):
        comfy = runtime.load_module('execution_error_test', 'comfyui_gen.py')
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            'task': {'status': {'status_str': 'error', 'completed': False}},
        }).encode()
        with patch.object(comfy.time, 'sleep'), \
             patch.object(comfy.urllib.request, 'urlopen', return_value=response):
            with self.assertRaises(RuntimeError):
                comfy.wait_for_result('task', 10)

    def test_shared_profiles_both_inject_the_prompt_and_dimensions(self):
        comfy = runtime.load_module('shared_profiles_test', 'comfyui_gen.py')
        for profile in ('z-image', 'flux2'):
            with self.subTest(profile=profile):
                workflow = comfy.load_workflow(
                    comfy.resolve_workflow_path(None, profile), 'visual requirement',
                    width=1024, height=432, seed=42,
                )
                positive, negative, found = comfy._find_prompt_node_ids(workflow)
                self.assertTrue(found)
                self.assertTrue(positive)
                self.assertTrue(all(workflow[node]['inputs']['text'] == 'visual requirement' for node in positive))


if __name__ == '__main__':
    unittest.main()
