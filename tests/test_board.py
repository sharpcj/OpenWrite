"""Real-time storyboard: read-only aggregation, filters, pagination, HTTP API."""
import layout
from functools import partial
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

import board
import workflow
from test_rednote import finish

ROOT = Path(__file__).resolve().parents[1]


def make_task(root, name, platform='wechat', created=None, complete=False):
    article = root / 'articles' / name
    article.mkdir(parents=True)
    if complete:
        finish(article)
        workflow.complete_format(article, 'indigo', False,
                                 workflow.check_publishable(article, workflow.load(article)))
    else:
        workflow.initialize(article, f'{name} 标题', 'blogger', platform, {})
        workflow.write_json(layout.path(article, 'sources.json'), {'version': 1, 'sources': [
            {'id': 's1', 'title': '用户资料', 'kind': 'user', 'content': '实际资料内容'},
        ]})
        workflow.complete(article, 'search')
    if created:
        state = workflow.load(article)
        state['created_at'] = created
        workflow.write_json(layout.path(article, 'workflow.json'), state)
    return article


class AggregationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-board-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / 'articles').mkdir()

    def test_new_tasks_record_created_at_and_legacy_falls_back(self):
        article = make_task(self.root, 'fresh')
        state = workflow.load(article)
        self.assertIn('created_at', state)
        summary = board.summarize(article)
        self.assertEqual(summary['created_at'], state['created_at'])
        legacy = make_task(self.root, 'legacy')
        state = workflow.load(legacy)
        del state['created_at']
        workflow.write_json(layout.path(legacy, 'workflow.json'), state)
        self.assertTrue(board.summarize(legacy)['created_at'])

    def test_sort_desc_and_platform_and_date_filters(self):
        make_task(self.root, 'old-wechat', 'wechat', created='2026-11-01T10:00:00+08:00')
        make_task(self.root, 'new-rednote', 'rednote', created='2026-11-15T10:00:00+08:00')
        make_task(self.root, 'mid-wechat', 'wechat', created='2026-11-10T10:00:00+08:00')
        tasks = board.collect_tasks(self.root)
        self.assertEqual([t['name'] for t in tasks], ['new-rednote', 'mid-wechat', 'old-wechat'])
        self.assertEqual([t['name'] for t in board.collect_tasks(self.root, platform='wechat')],
                         ['mid-wechat', 'old-wechat'])
        ranged = board.collect_tasks(self.root, date_from='2026-11-05', date_to='2026-11-12')
        self.assertEqual([t['name'] for t in ranged], ['mid-wechat'])

    def test_pagination_boundaries(self):
        for index in range(board.PAGE_SIZE + 3):
            make_task(self.root, f'task-{index:02d}', created=f'2026-11-{index + 1:02d}T10:00:00+08:00')
        first = board.paginate(board.collect_tasks(self.root), 1)
        self.assertEqual((first['total'], first['pages'], len(first['items'])),
                         (board.PAGE_SIZE + 3, 2, board.PAGE_SIZE))
        last = board.paginate(board.collect_tasks(self.root), 99)
        self.assertEqual((last['page'], len(last['items'])), (2, 3))

    def test_detail_steps_and_deliverables_gate(self):
        article = make_task(self.root, 'progress')
        detail = board.task_detail(self.root, 'progress')
        self.assertEqual(detail['steps'][0]['step'], 'direction')
        self.assertEqual(detail['steps'][0]['status'], 'done')
        self.assertEqual(detail['steps'][1]['status'], 'done')
        self.assertEqual(detail['steps'][2]['status'], 'current')
        self.assertEqual(detail['steps'][3]['status'], 'pending')
        self.assertEqual(detail['steps'][-1]['step'], 'published')
        self.assertEqual(detail['steps'][-1]['status'], 'pending')
        self.assertIsNone(detail['deliverables'])
        completed = make_task(self.root, 'done-note', 'rednote', complete=True)
        detail = board.task_detail(self.root, 'done-note')
        self.assertTrue(detail['completed'])
        self.assertTrue(all(step['status'] == 'done' for step in detail['steps'][1:8]))
        self.assertEqual(detail['steps'][-1]['status'], 'current')  # 完成但未发布
        files = [image['file'] for image in detail['deliverables']['images']]
        self.assertEqual(files, ['xhs-01-cover.png', 'xhs-02-page.png'])
        self.assertTrue(all(image['exists'] for image in detail['deliverables']['images']))
        self.assertIsNotNone(detail['deliverables']['note'])
        workflow.write_json(layout.path(completed, 'publish-record.json'), {
            'version': 1, 'platform': 'rednote', 'title': 't', 'visibility': 'private',
            'published_at': '2026-11-17T12:00:00+08:00'})
        detail = board.task_detail(self.root, 'done-note')
        self.assertEqual(detail['steps'][-1]['status'], 'done')
        self.assertIn('仅自己可见', detail['steps'][-1]['note'])
        (layout.path(completed, 'cards.md')).write_text('# 卡片稿\n\n改了文案。\n', encoding='utf-8')
        detail = board.task_detail(self.root, 'done-note')
        self.assertEqual(detail['stale'], 'draft')
        self.assertEqual(detail['steps'][3]['status'], 'stale')
        self.assertEqual(detail['steps'][-1]['status'], 'done')  # 历史发布事实不因过期抹掉

    def test_uninitialized_detail_shows_direction_as_current(self):
        bare = self.root / 'articles/bare'
        bare.mkdir()
        detail = board.task_detail(self.root, 'bare')
        self.assertEqual(detail['steps'][0]['status'], 'current')
        self.assertEqual(detail['steps'][-1]['status'], 'pending')
        self.assertEqual(len(detail['steps']), len(workflow.STEPS) + 2)

    def test_uninitialized_and_invalid_tasks_do_not_crash(self):
        bare = self.root / 'articles/bare'
        bare.mkdir()
        self.assertEqual(board.summarize(bare)['error'], '未初始化工作流')
        broken = make_task(self.root, 'broken')
        (layout.path(broken, 'workflow.json')).write_text('{bad json', encoding='utf-8')
        self.assertIsNotNone(board.summarize(broken)['error'])
        self.assertEqual(len(board.collect_tasks(self.root)), 2)

    def test_overall_lifecycle_state(self):
        running = make_task(self.root, 'running')
        self.assertEqual((board.summarize(running)['overall'],
                          board.summarize(running)['overall_label']), ('generating', '生成中'))
        done = make_task(self.root, 'done', 'rednote', complete=True)
        self.assertEqual((board.summarize(done)['overall'],
                          board.summarize(done)['overall_label']), ('pending-publish', '待发布'))
        (layout.path(done, 'cards.md')).write_text('# 卡片稿\n\n改了文案。\n', encoding='utf-8')
        summary = board.summarize(done)
        self.assertEqual(summary['stale'], 'draft')  # 过期只作提示，不占徽章状态
        self.assertEqual((summary['overall'], summary['overall_label']), ('pending-publish', '待发布'))
        workflow.write_json(layout.path(done, 'publish-record.json'), {
            'version': 1, 'platform': 'rednote', 'title': 't', 'visibility': 'private',
            'published_at': '2026-11-17T12:00:00+08:00'})
        self.assertEqual((board.summarize(done)['overall'],
                          board.summarize(done)['overall_label']), ('published', '已发布'))
        bare = self.root / 'articles/bare'
        bare.mkdir()
        self.assertEqual((board.summarize(bare)['overall'],
                          board.summarize(bare)['overall_label']), ('ungenerated', '未生成'))
        broken = make_task(self.root, 'broken')
        (layout.path(broken, 'workflow.json')).write_text('{bad json', encoding='utf-8')
        self.assertEqual((board.summarize(broken)['overall'],
                          board.summarize(broken)['overall_label']), ('ungenerated', '未生成'))
        detail = board.task_detail(self.root, 'running')
        self.assertEqual(detail['overall'], 'generating')


class BoardHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='openwrite-board-http-')
        cls.root = Path(cls.tmp.name).resolve()
        (cls.root / 'articles').mkdir()
        make_task(cls.root, 'note', 'rednote', complete=True, created='2026-11-15T10:00:00+08:00')
        make_task(cls.root, 'draft', 'wechat', created='2026-11-10T10:00:00+08:00')
        cls.httpd = ThreadingHTTPServer(('127.0.0.1', 0), partial(board.BoardHandler, root=cls.root))
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.httpd.server_address[1]}'

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()

    def get(self, path):
        with urlopen(self.base + path, timeout=10) as response:
            return response.status, response.headers.get('Content-Type'), response.read()

    def test_page_and_api_endpoints(self):
        status, kind, body = self.get('/')
        self.assertEqual((status, kind), (200, 'text/html; charset=utf-8'))
        self.assertIn('实时故事板'.encode('utf-8'), body)
        status, _, body = self.get('/api/tasks')
        data = json.loads(body)
        self.assertEqual(data['total'], 2)
        self.assertEqual(data['items'][0]['name'], 'note')  # 完成时间较新
        self.assertEqual(data['items'][0]['overall'], 'pending-publish')
        self.assertEqual(data['items'][1]['overall'], 'generating')
        status, _, body = self.get('/api/task/note')
        detail = json.loads(body)
        self.assertTrue(detail['completed'])
        self.assertEqual(detail['platform_label'], '小红书')
        status, kind, body = self.get('/files/note/xhs-01-cover.png')
        self.assertEqual((status, kind), (200, 'image/png'))
        self.assertTrue(body.startswith(b'\x89PNG'))

    def test_filters_and_pagination_via_query(self):
        _, _, body = self.get('/api/tasks?platform=wechat')
        self.assertEqual([t['name'] for t in json.loads(body)['items']], ['draft'])
        _, _, body = self.get('/api/tasks?page=2')
        self.assertEqual(json.loads(body)['page'], 1)  # 只有一页时收敛

    def test_path_traversal_and_unknown_paths_are_rejected(self):
        for path in ('/files/note/..%2F..%2Fpreferences.py',
                     '/files/note/../../preferences.py',
                     '/files/note/workflow.json',
                     '/api/task/..',
                     '/api/task/no-such-task'):
            with self.subTest(path=path):
                try:
                    status, _, _ = self.get(path)
                    self.assertIn(status, (400, 404))
                except HTTPError as error:
                    self.assertIn(error.code, (400, 404))
        try:
            self.get('/nope')
            self.fail('应当 404')
        except HTTPError as error:
            self.assertEqual(error.code, 404)

    def test_board_is_read_only(self):
        path = layout.path(self.root / 'articles/note', 'workflow.json')
        before = path.read_bytes()
        self.get('/api/tasks')
        self.get('/api/task/note')
        self.get('/files/note/xhs-01-cover.png')
        self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
