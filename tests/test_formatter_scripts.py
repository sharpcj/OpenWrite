"""Formatter debt cleanup: shared convert function, batch CLI and polling preview."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/wechat-article-formatter/scripts'


def load_module(name):
    spec = importlib.util.spec_from_file_location(f'formatter_test_{name}', SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(SCRIPTS))
core = load_module('markdown_to_html')
batch = load_module('batch_convert')
preview = load_module('preview_generator')

SAMPLE = '# 标题\n\n这是一个测试段落，包含English words。\n\n## 小节\n\n- 要点一\n- 要点二\n'


class ConvertFunctionTests(unittest.TestCase):
    def test_convert_markdown_applies_theme_and_removes_h1(self):
        html = core.convert_markdown(SAMPLE, 'default')
        self.assertIn('<section', html)
        self.assertNotIn('标题</h1>', html)
        self.assertIn('小节', html)

    def test_preformat_adds_spacing_and_can_be_disabled(self):
        formatted = core.convert_markdown(SAMPLE, 'default')
        raw = core.convert_markdown(SAMPLE, 'default', preformat=False)
        self.assertIn('测试段落，包含 English', formatted)
        self.assertIn('包含English', raw)

    def test_overrides_and_closing_block(self):
        html = core.convert_markdown(SAMPLE, 'default', overrides={'primary-color': '#A93226'},
                                     closing_md='**关注**我们')
        self.assertIn('#A93226', html)
        self.assertIn('关注', html)

    def test_unknown_theme_is_reported(self):
        with self.assertRaises(SystemExit):
            core.convert_markdown(SAMPLE, 'no-such-theme')


class BatchConvertTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-batch-')
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name).resolve()
        (self.source / 'a.md').write_text(SAMPLE, encoding='utf-8')
        (self.source / 'b.md').write_text(SAMPLE, encoding='utf-8')

    def test_batch_cli_converts_directory_with_yaml_theme(self):
        result = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'batch_convert.py'),
                                 '--input', str(self.source), '--theme', 'grace'],
                                cwd=SCRIPTS, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ('a.html', 'b.html'):
            html = (self.source / name).read_text(encoding='utf-8')
            self.assertIn('<section', html)
        self.assertIn('成功 2', result.stdout)

    def test_batch_reports_invalid_theme_before_converting(self):
        result = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'batch_convert.py'),
                                 '--input', str(self.source), '--theme', 'no-such-theme'],
                                cwd=SCRIPTS, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('不存在', result.stderr)
        self.assertFalse((self.source / 'a.html').exists())

    def test_batch_output_dir_and_recursive(self):
        nested = self.source / 'nested'
        nested.mkdir()
        (nested / 'c.md').write_text(SAMPLE, encoding='utf-8')
        out = self.source / 'out'
        converter = batch.BatchConverter(theme='simple', output_dir=str(out))
        files = converter.find_markdown_files(str(self.source), recursive=True)
        self.assertEqual(len(files), 3)
        converter.convert_batch(files, show_progress=False)
        self.assertEqual(converter.failed_count, 0)
        self.assertTrue((out / 'c.html').is_file())


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-preview-')
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name).resolve()
        self.input = self.source / 'article.md'
        self.input.write_text(SAMPLE, encoding='utf-8')
        self.output = self.source / 'preview/article.html'

    def test_convert_once_writes_themed_html(self):
        preview.convert_once(self.input, self.output, 'modern')
        self.assertIn('<section', self.output.read_text(encoding='utf-8'))

    def test_polling_watcher_reconverts_on_change_without_watchdog(self):
        stop = threading.Event()
        watcher = threading.Thread(target=preview.watch_and_convert,
                                   args=(self.input, self.output, 'default', stop), daemon=True)
        watcher.start()
        try:
            deadline = time.monotonic() + 10
            while not self.output.exists() and time.monotonic() < deadline:
                time.sleep(0.1)
            self.assertTrue(self.output.exists())
            time.sleep(1.1)  # 确保 mtime 分辨率内可区分
            self.input.write_text(SAMPLE + '\n新增段落。\n', encoding='utf-8')
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if '新增段落' in self.output.read_text(encoding='utf-8'):
                    break
                time.sleep(0.2)
            self.assertIn('新增段落', self.output.read_text(encoding='utf-8'))
        finally:
            stop.set()
            watcher.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
