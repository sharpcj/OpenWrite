"""Formatter debt cleanup: shared convert function, batch CLI and polling preview."""
import importlib.util
import re
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
    def test_all_builtin_themes_are_discovered_and_render(self):
        names = {theme['name'] for theme in core._list_themes()}
        for name in ('default', 'grace', 'modern', 'simple', 'blueprint-tech'):
            with self.subTest(theme=name):
                self.assertIn(name, names)
                html = core.convert_markdown(SAMPLE, name, preformat=False)
                self.assertIn('小节', html)
                self.assertNotRegex(html, r'\{[a-z][a-z-]*\}')

    def test_blueprint_uses_consistent_heading_quote_and_table_styles(self):
        text = ('# 全文标题\n\n# 第一节\n\n> 推荐做法。\n\n'
                '# 第二节\n\n> 正向案例。\n\n'
                '| 项目 | 说明 |\n| --- | --- |\n'
                '| 甲 | 一 |\n| 乙 | 二 |\n| 丙 | 三 |\n')
        html = core.convert_markdown(text, 'blueprint-tech', preformat=False)
        headings = re.findall(r'<h1 style="([^"]+)"', html)
        quotes = re.findall(r'<blockquote style="([^"]+)"', html)
        headers = re.findall(r'<th style="([^"]+)"', html)
        self.assertEqual(len(headings), 2)
        self.assertEqual(len(set(headings)), 1)
        self.assertIn('background:#667eea;', headings[0])
        self.assertNotIn('gradient', headings[0])
        self.assertEqual(len(quotes), 2)
        self.assertEqual(len(set(quotes)), 1)
        self.assertIn('border-left:4px solid #2e8b8b;', quotes[0])
        self.assertEqual(len(headers), 2)
        self.assertEqual(len(set(headers)), 1)
        self.assertIn('background:#667eea;', headers[0])
        self.assertEqual(re.findall(r'<tr(?: style="([^"]*)")?>', html),
                         ['', 'background:#ffffff;', 'background:#f8f9ff;', 'background:#ffffff;'])
        self.assertNotIn('#f5576c', html)

    def test_table_row_styles_are_optional_and_support_header(self):
        text = '| 项目 |\n| --- |\n| 甲 |\n| 乙 |\n'
        for name in ('default', 'grace', 'modern', 'simple'):
            with self.subTest(theme=name):
                html = core.convert_markdown(text, name, preformat=False)
                self.assertEqual(html.count('<tr>'), 3)
                self.assertNotIn('<tr style=', html)
        styles = core._build_styles({'styles': {'tr-head': 'background:#123456;'}})
        html = core._md_to_html(text, styles)
        self.assertIn('<tr style="background:#123456;">', html)

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


class PreformatQuoteTests(unittest.TestCase):
    """回归：既有中文引号不得被奇偶配对 heuristic 翻转。"""

    def test_existing_corner_brackets_stay_paired(self):
        text = '弹窗来了：「开通会员」。两个「剪映平替」：「免费」与「开源」。\n'
        self.assertEqual(core._preformat_markdown(text), text)

    def test_ascii_paired_quotes_convert_to_corner_brackets(self):
        self.assertEqual(core._preformat_markdown('他说"你好"吗'), '他说「你好」吗')

    def test_mixed_existing_and_ascii_quotes_pair_independently(self):
        text = '已有「甲」与「乙」，再加"丙"和"丁"。'
        self.assertEqual(core._preformat_markdown(text), '已有「甲」与「乙」，再加「丙」和「丁」。')

    def test_quotes_inside_code_are_untouched(self):
        text = '命令 `echo "hi"` 如下：\n\n```bash\necho "hi"\n```\n'
        self.assertEqual(core._preformat_markdown(text), text)

    def test_unpaired_ascii_quote_is_left_alone(self):
        text = '只有一个"引号，不成对。'
        self.assertEqual(core._preformat_markdown(text), text)

    def test_curly_quotes_are_untouched(self):
        text = '“弯引号”与‘单弯引号’保持原样。'
        self.assertEqual(core._preformat_markdown(text), text)


if __name__ == '__main__':
    unittest.main()
