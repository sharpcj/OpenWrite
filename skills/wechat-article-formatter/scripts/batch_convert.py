#!/usr/bin/env python3
"""批量转换 Markdown 文件为微信公众号 HTML（YAML 主题系统）。

底层能力脚本：独立使用时不享受 openwrite.py 的七步状态检查；
项目创作任务请统一使用 `python3 openwrite.py format <文章目录>`。
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sys
import time

from markdown_to_html import convert_markdown, _load_theme


class BatchConverter:
    """批量转换器：共用主题，逐文件调用核心转换函数。"""

    def __init__(self, theme: str = 'default', output_dir: str = None, workers: int = 4):
        self.theme = theme
        self.output_dir = Path(output_dir) if output_dir else None
        self.workers = workers
        self.total_files = 0
        self.success_count = 0
        self.failed_count = 0
        self.failed_files = []

    def find_markdown_files(self, input_path: str, recursive: bool = False) -> list:
        path = Path(input_path)
        if path.is_file():
            if path.suffix.lower() in ('.md', '.markdown'):
                return [path]
            print(f'警告: {path} 不是 Markdown 文件，已跳过')
            return []
        if path.is_dir():
            pattern = '**/*' if recursive else '*'
            return sorted({p for p in path.glob(pattern)
                           if p.suffix.lower() in ('.md', '.markdown')})
        raise FileNotFoundError(f'路径不存在: {input_path}')

    def convert_single_file(self, input_file: Path) -> tuple:
        try:
            if self.output_dir:
                output_file = self.output_dir / f'{input_file.stem}.html'
            else:
                output_file = input_file.with_suffix('.html')
            start_time = time.time()
            closing_path = input_file.parent / 'closing.md'
            closing_md = closing_path.read_text(encoding='utf-8') if closing_path.exists() else None
            html = convert_markdown(input_file.read_text(encoding='utf-8'), self.theme,
                                    closing_md=closing_md)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(html, encoding='utf-8')
            return True, input_file, output_file, time.time() - start_time
        except Exception as exc:
            return False, input_file, str(exc), 0

    def convert_batch(self, input_files: list, show_progress: bool = True) -> None:
        self.total_files = len(input_files)
        if not self.total_files:
            print('未找到 Markdown 文件')
            return
        print(f'找到 {self.total_files} 个 Markdown 文件；主题: {self.theme}；并发数: {self.workers}')
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            print(f'输出目录: {self.output_dir}')
        else:
            print('输出目录: 与源文件相同')
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {executor.submit(self.convert_single_file, file): file for file in input_files}
            for future in as_completed(futures):
                success, input_file, result, elapsed = future.result()
                if success:
                    self.success_count += 1
                    message = f'{input_file.name} → {Path(result).name} ({elapsed:.2f}s)'
                    status = 'OK'
                else:
                    self.failed_count += 1
                    self.failed_files.append((input_file, result))
                    message = f'{input_file.name} - 失败: {result}'
                    status = 'FAIL'
                if show_progress:
                    progress = f'[{self.success_count + self.failed_count}/{self.total_files}]'
                    print(f'{status} {progress} {message}')

    def print_summary(self) -> None:
        print(f'转换摘要：总数 {self.total_files}，成功 {self.success_count}，失败 {self.failed_count}')
        for file, error in self.failed_files:
            print(f'  失败: {file.name}: {error}')


def main() -> int:
    parser = argparse.ArgumentParser(
        description='批量转换 Markdown 文件为微信公众号 HTML',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例用法:
  python batch_convert.py --input article.md
  python batch_convert.py --input articles/ --recursive
  python batch_convert.py --input articles/ --output output/ --theme grace
  python batch_convert.py --input articles/ --workers 8

主题: default / grace / modern / simple，或 themes/ 下的自定义 YAML 主题名。
项目创作任务请使用 openwrite.py format，以启用七步状态检查。
        ''')
    parser.add_argument('-i', '--input', required=True, help='输入的 Markdown 文件或目录路径')
    parser.add_argument('-o', '--output', help='输出目录（默认：与源文件相同目录）')
    parser.add_argument('-t', '--theme', default='default', help='YAML 主题名（默认：default）')
    parser.add_argument('-r', '--recursive', action='store_true', help='递归查找子目录中的 Markdown 文件')
    parser.add_argument('-w', '--workers', type=int, default=4, help='并发转换的线程数（默认：4）')
    parser.add_argument('-q', '--quiet', action='store_true', help='静默模式，只显示摘要')
    args = parser.parse_args()

    try:
        _load_theme(args.theme)  # 主题全局提前校验，避免逐文件重复失败
        converter = BatchConverter(theme=args.theme, output_dir=args.output, workers=args.workers)
        markdown_files = converter.find_markdown_files(args.input, args.recursive)
        if not markdown_files:
            print('错误: 未找到 Markdown 文件', file=sys.stderr)
            return 1
        converter.convert_batch(markdown_files, show_progress=not args.quiet)
        converter.print_summary()
        return 0 if converter.failed_count == 0 else 1
    except Exception as exc:
        print(f'错误: 批量转换失败: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
