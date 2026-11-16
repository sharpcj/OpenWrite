"""Read-only real-time storyboard over article workspaces.

Left pane: paginated task list (created date desc, date-range and platform
filters). Right pane: the selected task's creation board — title, subtitle
(platform / topic / perspective), seven-step progress, and deliverable
thumbnails once the task is complete.

Aggregates existing files only; never writes workflow state and never reads
credentials. Standard library only; the browser polls for live updates.
"""
from __future__ import annotations

from datetime import datetime
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from urllib.parse import parse_qs, unquote, urlparse
import webbrowser

import platforms
import preferences
import workflow

ROOT = Path(__file__).resolve().parent
PAGE_SIZE = 12
FILE_PATTERN = re.compile(r'[\w-]+\.(png|jpg|jpeg|html|md)')
NAME_PATTERN = re.compile(r'[\w-]{1,100}')
CONTENT_TYPES = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                 '.html': 'text/html; charset=utf-8', '.md': 'text/plain; charset=utf-8'}


def task_created(state: dict, path: Path) -> str:
    """New tasks carry created_at; legacy tasks fall back to the state file mtime."""
    created = state.get('created_at')
    if isinstance(created, str) and created:
        return created
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec='seconds')
    except OSError:
        return ''


def brief_topic(article: Path) -> str:
    try:
        text = (article / 'brief.md').read_text(encoding='utf-8')
    except OSError:
        return ''
    match = re.search(r'(?m)^-\s*主题[:：]\s*(.+)$', text)
    return match.group(1).strip() if match else ''


def summarize(article: Path) -> dict:
    summary = {'name': article.name, 'title': article.name, 'platform': '', 'platform_label': '',
               'perspective': '', 'perspective_label': '', 'topic': '', 'created_at': '',
               'done': 0, 'total': len(workflow.STEPS), 'completed': False,
               'stale': None, 'error': None}
    path = article / 'workflow.json'
    if not path.is_file():
        summary['error'] = '未初始化工作流'
        summary['created_at'] = task_created({}, article)
        return summary
    try:
        state = workflow.load(article)
    except (OSError, ValueError) as exc:
        summary['error'] = str(exc)
        summary['created_at'] = task_created({}, path)
        return summary
    platform = preferences.task_platform(state)
    perspective = preferences.task_perspective(state)
    summary.update({
        'title': state.get('title') or article.name,
        'platform': platform,
        'platform_label': preferences.PLATFORM_LABELS.get(platform, platform),
        'perspective': perspective,
        'perspective_label': preferences.PERSPECTIVE_LABELS.get(perspective, perspective),
        'topic': brief_topic(article) or state.get('title') or article.name,
        'created_at': task_created(state, path),
        'done': len(state['completed']),
        'completed': len(state['completed']) == len(workflow.STEPS),
    })
    try:
        stale = workflow.stale_step(article, state)
        summary['stale'] = stale[0] if stale else None
    except (OSError, ValueError):
        summary['stale'] = None
    return summary


def collect_tasks(root: Path, platform=None, date_from=None, date_to=None) -> list:
    articles = root / 'articles'
    tasks = []
    if articles.is_dir():
        for article in articles.iterdir():
            if not article.is_dir() or article.name.startswith('.'):
                continue
            summary = summarize(article)
            if platform and summary['platform'] != platform:
                continue
            day = summary['created_at'][:10]
            if date_from and day and day < date_from:
                continue
            if date_to and day and day > date_to:
                continue
            tasks.append(summary)
    tasks.sort(key=lambda item: (item['created_at'], item['name']), reverse=True)
    return tasks


def paginate(tasks: list, page: int) -> dict:
    total = len(tasks)
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(1, min(page, pages))
    return {'items': tasks[(page - 1) * PAGE_SIZE:page * PAGE_SIZE],
            'page': page, 'pages': pages, 'total': total, 'page_size': PAGE_SIZE}


def deliverables(article: Path, state: dict) -> dict:
    """Deliverable files for a completed task; missing files are flagged, not hidden."""
    profile = platforms.for_state(state)
    images = []

    def entry(name: str, role: str) -> dict:
        return {'file': name, 'role': role, 'exists': (article / name).is_file()}

    try:
        requests = workflow.requests(article)
        cover = next(item for item in requests if item['role'] == 'cover')
        images.append(entry(cover['output'], 'cover'))
        content = [item for item in requests if item['role'] == 'content']
        if profile['rendered_artifact'] is None:
            content.sort(key=lambda item: item['order'])
        images.extend(entry(item['output'], 'content') for item in content)
    except (OSError, ValueError):
        images.append(entry(profile['cover']['output'], 'cover'))
    result = {'images': images, 'html': None, 'note': None}
    if profile['rendered_artifact']:
        if (article / profile['rendered_artifact']).is_file():
            result['html'] = profile['rendered_artifact']
    else:
        try:
            result['note'] = workflow.note_parts(article)
        except (OSError, ValueError):
            pass
    return result


def task_detail(root: Path, name: str) -> dict:
    if not NAME_PATTERN.fullmatch(name):
        raise ValueError('非法文章目录名')
    article = root / 'articles' / name
    if not article.is_dir():
        raise ValueError(f'文章目录不存在：{name}')
    detail = dict(summarize(article))
    detail['steps'] = []
    detail['deliverables'] = None
    if detail['error']:
        return detail
    state = workflow.load(article)
    labels = platforms.step_labels(state)
    done = len(state['completed'])
    stale_index = workflow.STEPS.index(detail['stale']) if detail['stale'] else None
    for index, (step, label) in enumerate(zip(workflow.STEPS, labels)):
        record = state['completed'][index] if index < done else None
        if record is None:
            status = 'current' if index == done else 'pending'
        elif stale_index is not None and index >= stale_index:
            status = 'stale'
        else:
            status = 'done'
        detail['steps'].append({'step': step, 'label': label, 'status': status,
                                'note': (record or {}).get('note', '')})
    if detail['completed']:
        detail['deliverables'] = deliverables(article, state)
    return detail


class BoardHandler(BaseHTTPRequestHandler):
    """Localhost-only read-only board: page, JSON API and artifact files."""

    def __init__(self, *args, root: Path = None, **kwargs):
        self.root = root or ROOT
        super().__init__(*args, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == '/':
                self._send(200, 'text/html; charset=utf-8', (ROOT / 'board.html').read_bytes())
            elif parsed.path == '/api/tasks':
                query = parse_qs(parsed.query)
                tasks = collect_tasks(self.root,
                                      platform=query.get('platform', [None])[0] or None,
                                      date_from=query.get('from', [None])[0] or None,
                                      date_to=query.get('to', [None])[0] or None)
                try:
                    page = int(query.get('page', ['1'])[0])
                except ValueError:
                    page = 1
                self._json(paginate(tasks, page))
            elif parsed.path.startswith('/api/task/'):
                self._json(task_detail(self.root, unquote(parsed.path[len('/api/task/'):])))
            elif parsed.path.startswith('/files/'):
                self._serve_file(unquote(parsed.path[len('/files/'):]))
            else:
                self._send(404, 'text/plain; charset=utf-8', 'Not Found'.encode('utf-8'))
        except ValueError as exc:
            self._json({'error': str(exc)}, status=400)
        except OSError as exc:
            self._json({'error': str(exc)}, status=500)

    def _serve_file(self, relative: str):
        parts = relative.split('/', 1)
        if len(parts) != 2 or not NAME_PATTERN.fullmatch(parts[0]) or not FILE_PATTERN.fullmatch(parts[1]):
            raise ValueError('非法文件路径')
        base = (self.root / 'articles').resolve()
        path = (base / parts[0] / parts[1]).resolve()
        if path.is_symlink() or base not in path.parents or not path.is_file():
            raise ValueError('文件不存在或不允许访问')
        self._send(200, CONTENT_TYPES[path.suffix.lower()], path.read_bytes())

    def _json(self, value: dict, status: int = 200):
        import json
        self._send(status, 'application/json; charset=utf-8',
                   json.dumps(value, ensure_ascii=False).encode('utf-8'))

    def _send(self, status: int, content_type: str, body: bytes):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def serve(root: Path, port: int = 8765, open_browser: bool = True) -> None:
    server = ThreadingHTTPServer(('127.0.0.1', port), partial(BoardHandler, root=root))
    url = f'http://127.0.0.1:{server.server_address[1]}'
    print(f'实时故事板已启动：{url}（只读，不修改任何任务状态；Ctrl+C 停止）')
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n故事板已停止')
    finally:
        server.server_close()
