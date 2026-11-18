"""Real journal/locks with fake HTTP only; no config, credentials or network."""
from copy import deepcopy
import importlib.util
import io
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from wechat_reliability import ReliableDraft, article_lock, atomic_json, verify

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('reliable_publisher_test', ROOT / 'skills/wechat-draft-publisher/publisher.py')
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReliableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.article = Path(self.temp.name)
        self.cover = self.article / 'cover.png'
        self.cover.write_bytes(b'cover')
        (self.article / 'one.png').write_bytes(b'one')
        (self.article / 'two.png').write_bytes(b'two')
        self.html = '<p>First &amp; text</p><img src="one.png"><p>Second</p><img src="two.png">'
        self.publisher = module.WeChatPublisher.__new__(module.WeChatPublisher)
        self.publisher.appid = 'wx-offline-test'
        self.publisher.get_access_token = Mock(return_value='synthetic-test-token')
        self.publisher.config_file = self.article / 'nonexistent-config'
        self.engine = ReliableDraft(self.publisher, self.article / 'workflow')
        self.posts = []
        self.remote = {}
        self.uploads = 0
        self.adds = 0
        self.failure = None
        self.read_mutation = None
        self.patch = patch.object(module.requests, 'post', side_effect=self.http)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.sleep = patch('wechat_reliability.time.sleep')
        self.sleep.start()
        self.addCleanup(self.sleep.stop)

    def http(self, url, **kwargs):
        operation = url.rsplit('/', 1)[-1]
        self.posts.append(operation)
        if operation == 'add_material':
            self.uploads += 1
            if self.failure == 'image' and self.uploads == 3:
                raise OSError('offline upload failure')
            data = {'media_id': 'image-' + str(self.uploads),
                    'url': 'https://example.invalid/image-' + str(self.uploads)}
        elif operation == 'add':
            self.adds += 1
            payload = json.loads(kwargs['data'])
            self.remote['draft-1'] = deepcopy(payload['articles'][0])
            # The server may commit even when no response reaches the caller.
            if self.failure == 'timeout':
                raise TimeoutError('simulated committed timeout')
            if self.failure == 'interrupt':
                raise KeyboardInterrupt()
            data = {'media_id': 'draft-1'}
        elif operation == 'get':
            state = self.state()
            entries = list(state['versions'].values())
            self.assertTrue(any(e.get('media_id') for e in entries), 'ID must be durable before read')
            media_id = json.loads(kwargs['data'])['media_id']
            data = {'news_item': [deepcopy(self.remote[media_id])]}
            if self.read_mutation:
                self.read_mutation(data['news_item'][0])
        elif operation == 'batchget':
            data = {'item': [], 'total_count': 0, 'item_count': 0}
        else:
            raise AssertionError('unexpected HTTP operation ' + operation)
        response = Mock()
        response.json.return_value = data
        return response

    def state(self):
        return json.loads(self.engine.path.read_text())

    def publish(self, **kwargs):
        options = dict(title='Title', content=self.html, author='Author', cover=str(self.cover), digest='Digest')
        options.update(kwargs)
        return self.engine.publish(**options)

    def test_success_and_same_fingerprint_only_read(self):
        first = self.publish()
        self.assertEqual(first['status'], 'verified')
        self.assertEqual((self.adds, self.uploads), (1, 3))
        self.posts.clear()
        self.assertEqual(self.publish()['media_id'], 'draft-1')
        self.assertEqual(self.posts, ['get'])
        record = json.loads((self.engine.directory / 'publish-record.json').read_text())
        self.assertEqual(record['media_id'], 'draft-1')
        self.assertEqual(record['fingerprint'], first['fingerprint'])
        self.assertEqual(record['visibility'], 'draft')

    def test_each_asset_is_durable_and_resume_reuses_successes(self):
        self.failure = 'image'
        with self.assertRaises(ValueError):
            self.publish()
        self.assertEqual(len(self.state()['assets']), 2)
        self.assertEqual(self.adds, 0)
        self.assertFalse((self.engine.directory / 'publish-record.json').exists())
        self.failure = None
        self.publish()
        self.assertEqual(self.uploads, 4)  # failed third image only is uploaded again
        self.assertEqual(len(self.state()['assets']), 3)

    def test_timeout_unknown_blocks_changed_content_and_binds_old_request(self):
        self.failure = 'timeout'
        with self.assertRaises(TimeoutError):
            self.publish()
        entry = next(iter(self.state()['versions'].values()))
        self.assertEqual(entry['status'], 'unknown')
        for kwargs in ({}, {'title': 'changed'}, {'content': '<p>new</p>'}):
            with self.assertRaises(ValueError):
                self.publish(**kwargs)
        before = (self.adds, self.uploads)
        self.publisher.appid = 'another-account'
        with self.assertRaises(ValueError):
            self.publish()
        self.publisher.appid = 'wx-offline-test'
        self.failure = None
        recovered = self.publish(title='changed', resume_fingerprint=entry['fingerprint'], bind_media_id='draft-1')
        self.assertEqual(recovered['status'], 'verified')
        self.assertEqual((self.adds, self.uploads), before)

    def test_interruption_and_process_death_in_flight_recovery(self):
        self.failure = 'interrupt'
        with self.assertRaises(KeyboardInterrupt):
            self.publish()
        state = self.state()
        entry = next(iter(state['versions'].values()))
        self.assertEqual(entry['status'], 'unknown')
        entry['status'] = 'in_flight'
        atomic_json(self.engine.path, state)
        with self.assertRaises(ValueError):
            self.publish()
        self.assertEqual(next(iter(self.state()['versions'].values()))['status'], 'unknown')
        self.assertEqual(self.adds, 1)

    def test_verification_failure_only_retries_reads_and_preserves_id(self):
        self.read_mutation = lambda article: article.update(title='wrong')
        with self.assertRaises(ValueError):
            self.publish()
        self.assertEqual(self.posts.count('get'), 3)
        self.assertEqual(next(iter(self.state()['versions'].values()))['media_id'], 'draft-1')
        self.assertFalse((self.engine.directory / 'publish-record.json').exists())
        with self.assertRaises(ValueError):
            self.publish(title='changed')
        self.posts.clear()
        self.read_mutation = None
        self.publish()
        self.assertEqual(self.posts, ['get'])
        self.assertEqual(self.adds, 1)

    def test_all_metadata_body_order_image_identity_and_cover_are_checked(self):
        expected = {'title': 'T', 'author': 'A', 'digest': 'D', 'thumb_media_id': 'cover',
                    'content': '<p>one</p><img src="https://host/a"><p>two</p><img src="https://host/b">'}
        for field in ('title', 'author', 'digest', 'thumb_media_id'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify(expected, {'news_item': [dict(expected, **{field: 'wrong'})]})
        for html in ('<p>two</p><img src="https://host/a"><p>one</p><img src="https://host/b">',
                     '<p>one</p><img src="https://host/b"><p>two</p><img src="https://host/a">',
                     '<p>one</p><img src="https://host/x"><p>two</p><img src="https://host/b">'):
            with self.assertRaises(ValueError):
                verify(expected, {'news_item': [dict(expected, content=html)]})
        with self.assertRaises(ValueError):
            verify(expected, {'news_item': [expected, expected]})
        verify(dict(expected, content='<p>A &amp; B</p><img alt="x" src="https://host/a">'),
               {'news_item': [dict(expected, content="<p>A &#38; B</p><img src='https://host/a' alt='x' />")]})

    def test_readback_accepts_only_limited_wechat_image_url_variants(self):
        expected = {'title': 'T', 'author': 'A', 'digest': 'D', 'thumb_media_id': 'cover',
                    'content': '<p>text</p><img alt="diagram" src="http://mmbiz.qpic.cn/mmbiz_png/asset/0?wx_fmt=png">'}
        equivalent = '<p>text</p><img alt="diagram" data-src="https://mmbiz.qpic.cn/mmbiz_png/asset/640?wx_fmt=png">'
        verify(expected, {'news_item': [dict(expected, content=equivalent)]})
        for wrong in (
                equivalent.replace('/asset/', '/different/'),
                equivalent.replace('wx_fmt=png', 'wx_fmt=jpeg'),
                equivalent.replace('mmbiz.qpic.cn', 'mmbiz.qpic.cn.evil.invalid'),
                equivalent.replace('/640?', '/300?'),
                equivalent.replace('>text<', '>changed<')):
            with self.subTest(html=wrong), self.assertRaises(ValueError):
                verify(expected, {'news_item': [dict(expected, content=wrong)]})
        arbitrary = dict(expected, content='<img src="http://example.invalid/image/0">')
        with self.assertRaises(ValueError):
            verify(arbitrary, {'news_item': [dict(arbitrary, content='<img src="https://example.invalid/image/640">')]})

    def test_missing_image_and_unquoted_local_src_fail_closed(self):
        for html in ('<img src="missing.png">', '<img src=one.png>'):
            with self.subTest(html=html), self.assertRaises((ValueError, FileNotFoundError)):
                self.publish(content=html)
        self.assertEqual(self.adds, 0)

    def test_candidates_absence_never_unblocks_unknown(self):
        self.failure = 'timeout'
        with self.assertRaises(TimeoutError):
            self.publish()
        self.assertEqual(self.publish(list_candidates=True)['item'], [])
        with self.assertRaises(ValueError):
            self.publish()
        self.assertEqual(self.adds, 1)

    def test_new_version_and_account_use_correct_asset_scope_keep_history(self):
        first = self.publish()
        self.publish(title='version two')
        self.assertEqual(self.uploads, 3)
        self.assertEqual(len(self.state()['versions']), 2)
        self.assertIn(first['fingerprint'], self.state()['versions'])
        self.publisher.appid = 'other-appid'
        self.publish(title='version three')
        self.assertEqual(self.uploads, 6)
        self.assertEqual(len(self.state()['versions']), 3)

    def test_atomic_failure_keeps_prior_json(self):
        path = self.article / 'atomic.json'
        atomic_json(path, {'old': True})
        with patch('wechat_reliability.os.replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                atomic_json(path, {'new': True})
        self.assertEqual(json.loads(path.read_text()), {'old': True})
        self.assertEqual(list(self.article.glob('.atomic.json*')), [])

    def test_real_cross_process_lock_releases_without_stale_file(self):
        command = [sys.executable, '-c',
                   'from wechat_reliability import article_lock; import sys; '
                   '\nwith article_lock(sys.argv[1]): print("acquired")', str(self.engine.directory)]
        with article_lock(self.engine.directory):
            result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('另一进程', result.stderr)
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_add_token_error_is_not_replayed(self):
        response = Mock()
        response.json.return_value = {'errcode': 42001}
        with patch.object(module.requests, 'post', return_value=response) as post:
            with self.assertRaises(ValueError):
                self.publisher.draft_request('add', {'articles': []})
        self.assertEqual(post.call_count, 1)
        self.publisher.get_access_token.assert_called_with(force_refresh=True)

    def test_final_metadata_fingerprint_reuses_identical_truncated_payload(self):
        first = self.publish(title='x' * 64 + 'a')
        second = self.publish(title='x' * 64 + 'b')
        self.assertEqual(first['fingerprint'], second['fingerprint'])
        self.assertEqual(self.adds, 1)

    def test_binding_wrong_candidate_does_not_let_changed_content_bypass_block(self):
        self.failure = 'timeout'
        with self.assertRaises(TimeoutError):
            self.publish()
        key = next(iter(self.state()['versions']))
        with self.assertRaises(ValueError):
            self.publish(resume_fingerprint=key, bind_media_id='wrong-id')
        with self.assertRaises(ValueError):
            self.publish(title='changed')
        self.failure = None
        self.publish(resume_fingerprint=key, bind_media_id='draft-1')
        with self.assertRaises(ValueError):
            self.publish(resume_fingerprint=key, bind_media_id='replacement')
        self.assertEqual(self.adds, 1)

    def test_created_id_cannot_be_made_replaceable_by_same_id_binding(self):
        entry = self.publish()
        self.publish(resume_fingerprint=entry['fingerprint'], bind_media_id='draft-1')
        self.read_mutation = lambda article: article.update(digest='mismatch')
        with self.assertRaises(ValueError):
            self.publish()
        with self.assertRaises(ValueError):
            self.publish(resume_fingerprint=entry['fingerprint'], bind_media_id='replacement')

    def test_changed_image_creates_new_version_not_mixed_assets(self):
        first = self.publish()
        (self.article / 'one.png').write_bytes(b'new-one')
        second = self.publish()
        self.assertNotEqual(first['fingerprint'], second['fingerprint'])
        self.assertEqual(self.uploads, 4)
        self.assertEqual(len(self.state()['versions']), 2)

    def test_real_cli_main_uses_journal_and_only_verified_success(self):
        content = self.article / 'article.html'
        content.write_text(self.html)
        arguments = ['publisher.py', '--title', 'Title', '--author', 'Author',
                     '--digest', 'Digest', '--content', str(content), '--cover', str(self.cover)]
        with patch.object(module, 'WeChatPublisher', return_value=self.publisher), \
                patch.object(sys, 'argv', arguments), redirect_stdout(io.StringIO()) as output:
            module.main()
        self.assertIn('(verified)', output.getvalue())
        self.assertEqual(self.adds, 1)

    def test_in_flight_journal_failure_prevents_any_create_request(self):
        save = self.engine.save
        def fail_in_flight(entry=None):
            if entry and entry['status'] == 'in_flight':
                raise OSError('disk full')
            return save(entry)
        with patch.object(self.engine, 'save', side_effect=fail_in_flight):
            with self.assertRaises(OSError):
                self.publish()
        self.assertEqual(self.adds, 0)

    def test_root_exit_code_zero_without_verified_readback_cannot_write_record(self):
        import openwrite
        from argparse import Namespace
        manifest = {'title': 'Title', 'author': 'Author', 'digest': 'Digest'}
        (self.article / 'article.html').write_text(self.html)
        profile = {'rendered_artifact': 'article.html', 'cover': {'output': 'cover.png'},
                   'publisher': 'wechat-draft-publisher', 'publisher_entry': 'publisher.py'}
        args = Namespace(article=str(self.article), title=None, author=None, digest=None,
                         public=False, dry_run=False, headed=False, bind_media_id='id',
                         resume_fingerprint='fingerprint', list_draft_candidates=False)
        with patch.object(openwrite.workflow, 'require_publishable', return_value=manifest), \
                patch.object(openwrite.workflow, 'load', return_value={'account': 'account'}), \
                patch.object(openwrite.platforms, 'require_publish_adapter', return_value=profile), \
                patch.object(openwrite, 'run_skill', return_value=0) as run:
            self.assertEqual(openwrite.publish_article(args), 0)
        passed = run.call_args.args
        self.assertEqual(passed[passed.index('--bind-media-id') + 1], 'id')
        self.assertIn('--resume-fingerprint', passed)
        self.assertIn('--state-dir', passed)
        self.assertFalse((self.engine.directory / 'publish-record.json').exists())


    def test_token_preflight_failure_has_zero_add_and_can_retry(self):
        # Save successful assets, then exercise the real prefetch method failing.
        self.engine.load()
        for name in ('cover.png', 'one.png', 'two.png'):
            self.engine.upload(self.article / name)
        with patch.object(self.publisher, 'get_access_token', side_effect=OSError('token unavailable')):
            with self.assertRaises(OSError):
                self.publish()
        self.assertEqual(self.adds, 0)
        self.assertEqual(next(iter(self.state()['versions'].values()))['status'], 'preparing')
        self.assertFalse((self.engine.directory / 'publish-record.json').exists())
        self.publish()
        self.assertEqual((self.adds, self.uploads), (1, 3))

    def test_token_rejection_is_retryable_even_when_refresh_fails(self):
        from wechat_reliability import DraftRejected
        original = self.http
        def rejected(url, **kwargs):
            if url.endswith('/draft/add'):
                self.adds += 1
                response = Mock()
                response.json.return_value = {'errcode': 42001}
                return response
            return original(url, **kwargs)
        def token(force_refresh=False):
            if force_refresh:
                raise OSError('refresh unavailable')
            return 'prefetched-token'
        self.publisher.get_access_token.side_effect = token
        with patch.object(module.requests, 'post', side_effect=rejected):
            with self.assertRaises(DraftRejected):
                self.publish()
        self.assertEqual(next(iter(self.state()['versions'].values()))['status'], 'rejected')
        self.assertEqual(self.adds, 1)
        self.assertFalse((self.engine.directory / 'publish-record.json').exists())
        self.publisher.get_access_token.side_effect = None
        self.publish()
        self.assertEqual((self.adds, self.uploads), (2, 3))

    def test_add_consumes_prefetched_token_without_second_lookup(self):
        self.publisher.prepare_draft_add()
        self.publisher.get_access_token.side_effect = AssertionError('second lookup')
        self.publisher.draft_request('add', {'articles': [{}]})
        self.assertEqual(self.adds, 1)

    def test_ambiguous_error_responses_remain_unknown(self):
        for result in ({'errcode': -1}, {'errcode': 99999}, {}):
            with self.subTest(result=result), tempfile.TemporaryDirectory() as directory:
                engine = ReliableDraft(self.publisher, directory)
                def response(url, **kwargs):
                    if url.endswith('/draft/add'):
                        reply = Mock()
                        reply.json.return_value = result
                        return reply
                    return self.http(url, **kwargs)
                with patch.object(module.requests, 'post', side_effect=response):
                    with self.assertRaises(ValueError):
                        engine.publish('Title', self.html, 'Author', str(self.cover))
                self.assertEqual(next(iter(json.loads(engine.path.read_text())['versions'].values()))['status'], 'unknown')

    def test_cli_recovery_without_title_content_cover_or_prompt(self):
        entry = self.publish()
        self.cover.unlink()
        self.posts.clear()
        for options in (['--resume-fingerprint', entry['fingerprint']], ['--list-draft-candidates']):
            arguments = ['publisher.py', '--interactive', '--state-dir', str(self.engine.directory), *options]
            with patch.object(module, 'WeChatPublisher', return_value=self.publisher), \
                    patch.object(sys, 'argv', arguments), \
                    patch('builtins.input', side_effect=AssertionError('no prompts')), \
                    redirect_stdout(io.StringIO()):
                module.main()
        self.assertEqual(self.posts, ['get', 'batchget'])
        self.assertEqual(self.adds, 1)

    def test_root_recovery_ignores_missing_or_stale_outputs_but_creation_is_gated(self):
        import openwrite
        from argparse import Namespace
        entry = self.publish()
        self.cover.unlink()
        profile = {'rendered_artifact': 'article.html', 'publisher': 'wechat-draft-publisher',
                   'publisher_entry': 'publisher.py'}
        args = Namespace(article=str(self.article), title=None, author=None, digest=None,
                         public=False, dry_run=False, headed=False, bind_media_id=None,
                         resume_fingerprint=entry['fingerprint'], list_draft_candidates=False)
        def run(*arguments):
            with patch.object(module, 'WeChatPublisher', return_value=self.publisher), \
                    patch.object(sys, 'argv', ['publisher.py', *arguments[2:]]), \
                    patch('builtins.input', side_effect=AssertionError('no prompts')), \
                    redirect_stdout(io.StringIO()):
                module.main()
            self.assertEqual(arguments[arguments.index('--account') + 1], 'task-account')
            return 0
        with patch.object(openwrite.workflow, 'require_publishable', side_effect=ValueError('stale or missing')) as gate, \
                patch.object(openwrite.workflow, 'load', return_value={'platform': 'wechat', 'account': 'task-account'}), \
                patch.object(openwrite.platforms, 'require_publish_adapter', return_value=profile), \
                patch.object(openwrite, 'run_skill', side_effect=run):
            for stale in (False, True):
                if stale:
                    (self.article / 'article.html').write_text('changed current HTML')
                self.assertEqual(openwrite.publish_article(args), 0)
            gate.assert_not_called()
            args.resume_fingerprint = None
            args.list_draft_candidates = True
            self.assertEqual(openwrite.publish_article(args), 0)
            gate.assert_not_called()
            args.list_draft_candidates = False
            args.resume_fingerprint = None
            args.bind_media_id = 'candidate'
            with self.assertRaisesRegex(ValueError, 'stale or missing'):
                openwrite.publish_article(args)
            args.bind_media_id = None
            with self.assertRaisesRegex(ValueError, 'stale or missing'):
                openwrite.publish_article(args)
        self.assertEqual(self.adds, 1)


if __name__ == '__main__':
    unittest.main()
