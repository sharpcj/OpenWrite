"""Read-only real-time storyboard over article workspaces.

Left pane, top to bottom: global totals (created WeChat / Rednote task counts,
unaffected by the selectors below), two per-account share pie charts (legacy
tasks without an account fall into an "unassigned" slice), platform and account
selectors (default WeChat / first account; account labels prefer the user-filled
name), a created-date range, and the filtered task list (paginated, created date
desc, no per-item platform badge). Each task is badged with its overall lifecycle
state (ungenerated / generating / pending-publish / published); the seven writing
steps all count as generating. Right pane: the selected task's creation board —
title, subtitle (overall state / platform / account / topic / perspective),
seven-step progress plus direction and publish nodes, and deliverable thumbnails
once the task is complete.

Aggregates existing files only; never writes workflow state and never reads
credentials. Standard library only; the browser polls for live updates.
"""
from __future__ import annotations
import layout

from datetime import datetime
from functools import partial
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
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
# 看板是长驻进程，导入的代码不会随磁盘更新；指纹覆盖启动时导入的模块与角色预设。
CODE_FILES = ('board.py', 'openwrite.py', 'workflow.py', 'preferences.py',
              'platforms.py', 'layout.py', 'writer_roles.py')


def code_fingerprint() -> str:
    digest = hashlib.sha256()
    for name in CODE_FILES:
        path = ROOT / name
        digest.update(path.read_bytes() if path.is_file() else b'')
    roles = ROOT / 'writer_roles'
    if roles.is_dir():
        for path in sorted(roles.glob('*.yaml')):
            digest.update(path.read_bytes())
    return digest.hexdigest()


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
        text = (layout.existing(article, 'brief.md')).read_text(encoding='utf-8')
    except OSError:
        return ''
    match = re.search(r'(?m)^-\s*主题[:：]\s*(.+)$', text)
    return match.group(1).strip() if match else ''


def summarize(article: Path) -> dict:
    summary = {'name': article.name, 'title': article.name, 'platform': '', 'platform_label': '',
               'account': '', 'perspective': '', 'perspective_label': '', 'topic': '', 'created_at': '',
               'done': 0, 'total': len(workflow.STEPS), 'completed': False,
               'stale': None, 'error': None,
               'overall': 'ungenerated', 'overall_label': '未生成'}
    path = layout.existing(article, 'workflow.json')
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
        'account': state.get('account') or '',
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
    if publish_record(article):
        summary['overall'], summary['overall_label'] = 'published', '已发布'
    elif summary['completed']:
        summary['overall'], summary['overall_label'] = 'pending-publish', '待发布'
    else:
        summary['overall'], summary['overall_label'] = 'generating', '生成中'
    return summary


def collect_tasks(root: Path, platform=None, account=None, date_from=None, date_to=None) -> list:
    articles = root / 'articles'
    tasks = []
    if articles.is_dir():
        for article in articles.iterdir():
            if not article.is_dir() or article.name.startswith('.'):
                continue
            summary = summarize(article)
            if platform and summary['platform'] != platform:
                continue
            if account and summary['account'] != account:
                continue
            day = summary['created_at'][:10]
            if date_from and day and day < date_from:
                continue
            if date_to and day and day > date_to:
                continue
            tasks.append(summary)
    tasks.sort(key=lambda item: (item['created_at'], item['name']), reverse=True)
    return tasks


UNASSIGNED = '__unassigned__'


def account_labels(root: Path) -> dict:
    """Per-platform account display labels: the user-filled name, else the key."""
    config = preferences.read_config(root)
    labels = {}
    for platform in preferences.PLATFORMS.values():
        accounts = (config.get(platform) or {}).get('accounts', {})
        labels[platform] = {key: (fields.get('name') or key) for key, fields in accounts.items()}
    return labels


def _platform_account(article: Path):
    """Lightweight read for stats: platform and account only, no artifact hashing."""
    path = layout.existing(article, 'workflow.json')
    if not path.is_file():
        return None
    try:
        state = workflow.load(article)
    except (OSError, ValueError):
        return None
    return preferences.task_platform(state), state.get('account') or ''


def collect_stats(root: Path) -> dict:
    """Global totals and per-account breakdown (unfiltered by date/account selectors)."""
    labels = account_labels(root)
    totals = {platform: 0 for platform in preferences.PLATFORMS.values()}
    counts = {platform: {} for platform in preferences.PLATFORMS.values()}
    articles = root / 'articles'
    if articles.is_dir():
        for article in articles.iterdir():
            if not article.is_dir() or article.name.startswith('.'):
                continue
            info = _platform_account(article)
            if info is None or info[0] not in totals:
                continue
            platform, account = info
            totals[platform] += 1
            bucket = account or UNASSIGNED
            counts[platform][bucket] = counts[platform].get(bucket, 0) + 1
    breakdown, options = {}, {}
    for platform in preferences.PLATFORMS.values():
        items = [{'account': key,
                  'label': '未指定账号' if key == UNASSIGNED else labels[platform].get(key, key),
                  'count': count} for key, count in counts[platform].items()]
        items.sort(key=lambda item: (-item['count'], item['label']))
        breakdown[platform] = items
        options[platform] = [{'key': key, 'label': label} for key, label in labels[platform].items()]
    return {'totals': totals, 'breakdown': breakdown, 'account_options': options}


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


def publish_record(article: Path):
    """发布记录存在且带时间戳才视为已发布；损坏或缺失一律不算。"""
    try:
        record = workflow.read_json(layout.existing(article, 'publish-record.json'))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) and record.get('published_at') else None


def task_detail(root: Path, name: str) -> dict:
    if not NAME_PATTERN.fullmatch(name):
        raise ValueError('非法文章目录名')
    article = root / 'articles' / name
    if not article.is_dir():
        raise ValueError(f'文章目录不存在：{name}')
    detail = dict(summarize(article))
    detail['steps'] = []
    detail['deliverables'] = None
    direction = {'step': 'direction', 'label': '制定写作方向', 'mark': '✎', 'note': ''}
    published = {'step': 'published', 'label': '已发布', 'mark': '□', 'note': ''}
    if detail['error']:
        direction['status'] = 'current'
        published['status'] = 'pending'
        detail['steps'] = [direction] + [
            {'step': step, 'label': label, 'status': 'pending', 'ordinal': index + 1, 'note': ''}
            for index, (step, label) in enumerate(zip(workflow.STEPS, workflow.LABELS))]
        detail['steps'].append(published)
        return detail
    state = workflow.load(article)
    labels = platforms.step_labels(state)
    done = len(state['completed'])
    stale_index = workflow.STEPS.index(detail['stale']) if detail['stale'] else None
    direction['status'] = 'done'
    detail['steps'].append(direction)
    for index, (step, label) in enumerate(zip(workflow.STEPS, labels)):
        record = state['completed'][index] if index < done else None
        if record is None:
            status = 'current' if index == done else 'pending'
        elif stale_index is not None and index >= stale_index:
            status = 'stale'
        else:
            status = 'done'
        detail['steps'].append({'step': step, 'label': label, 'status': status,
                                'ordinal': index + 1, 'note': (record or {}).get('note', '')})
    record = publish_record(article)
    if record:
        published['status'] = 'done'
        visibility = {'draft': '微信草稿箱', 'private': '仅自己可见', 'public': '公开'}.get(
            record.get('visibility'), record.get('visibility') or '')
        published['note'] = f"{record['published_at']} · {visibility}".strip(' ·')
    elif detail['completed'] and not detail['stale']:
        published['status'] = 'current'
    else:
        published['status'] = 'pending'
    detail['steps'].append(published)
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
                                      account=query.get('account', [None])[0] or None,
                                      date_from=query.get('from', [None])[0] or None,
                                      date_to=query.get('to', [None])[0] or None)
                try:
                    page = int(query.get('page', ['1'])[0])
                except ValueError:
                    page = 1
                self._json(paginate(tasks, page))
            elif parsed.path == '/api/stats':
                self._json(collect_stats(self.root))
            elif parsed.path == '/api/version':
                self._json({'fingerprint': getattr(self.server, 'board_fingerprint', '')})
            elif parsed.path.startswith('/api/task/'):
                self._json(task_detail(self.root, unquote(parsed.path[len('/api/task/'):])))
            elif parsed.path.startswith('/files/'):
                self._serve_file(unquote(parsed.path[len('/files/'):]))
            else:
                self._send(404, 'text/plain; charset=utf-8', 'Not Found'.encode('utf-8'))
        except ValueError as exc:
            self._json({'error': str(exc)}, status=400)
        except (BrokenPipeError, ConnectionResetError):
            pass  # 探活客户端超时断开，不是服务错误
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
    _restart_if_stale(port)
    try:
        server = ThreadingHTTPServer(('127.0.0.1', port), partial(BoardHandler, root=root))
    except OSError:
        if board_alive(port):
            print(f'端口 {port} 已有看板运行，复用现有实例，不重复启动')
            return
        raise
    server.board_fingerprint = code_fingerprint()
    url = f'http://127.0.0.1:{server.server_address[1]}'
    pid_file = _pid_file(port)
    pid_file.write_text(str(os.getpid()), encoding='utf-8')
    print(f'实时故事板已启动：{url}（只读，不修改任何任务状态；Ctrl+C 停止）')
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n故事板已停止')
    finally:
        server.server_close()
        if pid_file.is_file() and pid_file.read_text(encoding='utf-8').strip() == str(os.getpid()):
            pid_file.unlink(missing_ok=True)


def _pid_file(port: int) -> Path:
    return Path(tempfile.gettempdir()) / f'openwrite-board-{port}.pid'


def board_alive(port: int = 8765, timeout: float = 3.0) -> bool:
    """Probe the JSON API so a foreign process on the port is not mistaken for us.

    /api/tasks 需聚合全部任务并哈希产物，任务多时较慢；超时须宽于一次完整聚合。
    """
    from urllib.request import urlopen
    try:
        with urlopen(f'http://127.0.0.1:{port}/api/tasks', timeout=timeout) as response:
            return 'items' in json.loads(response.read())
    except (OSError, ValueError):
        return False


def board_current(port: int, timeout: float = 1.0) -> bool:
    """A live board is current only when its imported code matches this checkout.

    旧进程没有 /api/version（404）或指纹不符都视为过期，需要重启才能读懂新配置与状态。
    """
    from urllib.request import urlopen
    try:
        with urlopen(f'http://127.0.0.1:{port}/api/version', timeout=timeout) as response:
            return json.loads(response.read()).get('fingerprint') == code_fingerprint()
    except (OSError, ValueError):
        return False


def _restart_if_stale(port: int) -> None:
    if board_alive(port) and not board_current(port):
        stop_board(port)
        deadline = time.monotonic() + 3
        while board_alive(port, timeout=1.0) and time.monotonic() < deadline:
            time.sleep(0.1)


def stop_board(port: int = 8765) -> bool:
    pid_file = _pid_file(port)
    if not pid_file.is_file():
        return False
    try:
        pid = int(pid_file.read_text(encoding='utf-8').strip())
        os.kill(pid, signal.SIGTERM)
    except (OSError, ValueError):
        return False
    finally:
        pid_file.unlink(missing_ok=True)
    return True


def ensure_board(port: int = 8765, open_browser: bool = True):
    """Start the board detached if absent; reuse a live one. Returns (url, started).

    A live board whose imported code predates this checkout is stopped and
    restarted, so config/schema changes never leave a stale server behind.
    A per-port file lock serializes probe+spawn so concurrent task starts never
    leave two live servers: the loser of a bind race exits gracefully in serve()
    and this call reports reuse. The winning child opens the browser itself.
    """
    import fcntl
    url = f'http://127.0.0.1:{port}'
    lock_path = Path(tempfile.gettempdir()) / f'openwrite-board-{port}.lock'
    with open(lock_path, 'a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _restart_if_stale(port)
        if board_alive(port):
            if open_browser:
                webbrowser.open(url)
            return url, False
        log = Path(tempfile.gettempdir()) / f'openwrite-board-{port}.log'
        with open(log, 'ab') as handle:
            process = subprocess.Popen(
                [sys.executable, str(ROOT / 'openwrite.py'), 'board', '--port', str(port)],
                stdout=handle, stderr=handle, start_new_session=True)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if board_alive(port, timeout=2.0):
                break
            if process.poll() is not None:
                break
            time.sleep(0.1)
        if not board_alive(port, timeout=2.0):
            raise RuntimeError(f'看板启动失败，详见日志：{log}')
        return url, process.poll() is None
