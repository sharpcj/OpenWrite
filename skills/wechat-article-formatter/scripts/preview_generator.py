#!/usr/bin/env python3
"""实时预览生成器：边写边看微信公众号排版效果。

使用文件修改时间轮询（标准库，无额外依赖），修改 Markdown 后自动重新转换，
刷新浏览器即可看到最新效果。底层能力脚本，不享受 openwrite.py 的七步状态检查。
"""
from __future__ import annotations

import argparse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import sys
import threading
import time
import webbrowser

from markdown_to_html import convert_markdown

import layout


class QuietHTTPRequestHandler(SimpleHTTPRequestHandler):
    """静默的 HTTP 请求处理器（不打印访问日志）。"""

    def log_message(self, format, *args):
        pass


def convert_once(input_path: Path, output_file: Path, theme: str) -> None:
    closing_path = layout.existing(input_path.parent, 'closing.md')
    closing_md = closing_path.read_text(encoding='utf-8') if closing_path.exists() else None
    html = convert_markdown(input_path.read_text(encoding='utf-8'), theme, closing_md=closing_md)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(html, encoding='utf-8')


def watch_and_convert(input_path: Path, output_file: Path, theme: str, stop: threading.Event) -> None:
    """轮询文件修改时间，变化时重新转换；不依赖第三方文件监听库。"""
    last_modified = None
    while not stop.is_set():
        try:
            modified = input_path.stat().st_mtime
            if modified != last_modified:
                last_modified = modified
                convert_once(input_path, output_file, theme)
                print(f'[{time.strftime("%H:%M:%S")}] 已更新预览: {output_file.name}')
        except Exception as exc:
            print(f'[{time.strftime("%H:%M:%S")}] 转换失败: {exc}', file=sys.stderr)
        stop.wait(1)


def main() -> int:
    parser = argparse.ArgumentParser(
        description='实时预览 Markdown 文章的微信公众号效果',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例用法:
  python preview_generator.py --input article.md
  python preview_generator.py --input article.md --theme grace
  python preview_generator.py --input article.md --output preview/ --port 8080

工作原理:
  1. 首次运行时转换 Markdown 为 HTML
  2. 在浏览器中打开预览
  3. 轮询文件修改时间，变化时自动重新转换
  4. 刷新浏览器即可看到最新效果；按 Ctrl+C 停止
        ''')
    parser.add_argument('-i', '--input', required=True, help='输入的 Markdown 文件路径')
    parser.add_argument('-o', '--output', help='输出目录（默认：./preview/）')
    parser.add_argument('-t', '--theme', default='default', help='YAML 主题名（默认：default）')
    parser.add_argument('-p', '--port', type=int, default=8000, help='HTTP 服务器端口（默认：8000）')
    parser.add_argument('--no-browser', action='store_true', help='不自动打开浏览器')
    args = parser.parse_args()

    try:
        input_path = Path(args.input).expanduser().resolve()
        if not input_path.exists():
            raise FileNotFoundError(f'输入文件不存在: {args.input}')
        output_dir = Path(args.output) if args.output else Path('./preview')
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f'{input_path.stem}.html'

        print(f'监听文件: {input_path}')
        print(f'输出目录: {output_dir}；主题: {args.theme}')
        convert_once(input_path, output_file, args.theme)

        server = HTTPServer(('localhost', args.port), QuietHTTPRequestHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        print(f'本地服务器已启动: http://localhost:{args.port}')

        if not args.no_browser:
            preview_url = f'http://localhost:{args.port}/{output_file.name}'
            webbrowser.open(preview_url)
            print(f'已在浏览器中打开预览: {preview_url}')

        print('正在监听文件变化；修改 Markdown 后刷新浏览器即可。按 Ctrl+C 停止。')
        stop = threading.Event()
        watcher = threading.Thread(target=watch_and_convert,
                                   args=(input_path, output_file, args.theme, stop), daemon=True)
        watcher.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            stop.set()
            server.shutdown()
            print('\n预览服务已停止')
        return 0
    except Exception as exc:
        print(f'错误: 启动失败: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
