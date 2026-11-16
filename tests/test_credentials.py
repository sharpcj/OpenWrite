"""Local .env setup and WeChat credential loading; no network or home-directory config."""
from contextlib import redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import preferences

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ('WeChat=true\nSelfMediaBlogger=true\n'
            'WeChatAppID=\nWeChatAppSecret=\nWeChatAuthor=\n')
APPID = 'wx1234567890abcdef'


def load_publisher():
    path = ROOT / 'skills/wechat-draft-publisher/publisher.py'
    spec = importlib.util.spec_from_file_location('publisher_credentials_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EnvSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-credentials-')
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name).resolve()
        (self.project / '.env.example').write_text(TEMPLATE, encoding='utf-8')

    def test_setup_copies_template_once_with_owner_only_permissions(self):
        target, created = preferences.init_env(self.project)
        self.assertTrue(created)
        self.assertEqual(target, self.project / '.env')
        self.assertEqual(target.read_text(encoding='utf-8'), TEMPLATE)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        target.write_text('WeChatAppID=kept\n', encoding='utf-8')
        again, created = preferences.init_env(self.project)
        self.assertFalse(created)
        self.assertEqual(again.read_text(encoding='utf-8'), 'WeChatAppID=kept\n')

    def test_setup_requires_template_and_refuses_symlink(self):
        (self.project / '.env.example').unlink()
        with self.assertRaises(ValueError):
            preferences.init_env(self.project)
        (self.project / '.env.example').write_text(TEMPLATE, encoding='utf-8')
        outside = self.project / 'outside'
        outside.write_text('secret', encoding='utf-8')
        (self.project / '.env').symlink_to(outside)
        with self.assertRaises(ValueError):
            preferences.init_env(self.project)
        self.assertEqual(outside.read_text(encoding='utf-8'), 'secret')

    def test_cli_setup_creates_env_and_second_run_keeps_it(self):
        for name in ('openwrite.py', 'workflow.py', 'preferences.py'):
            shutil.copy2(ROOT / name, self.project / name)
        command = [sys.executable, '-B', str(self.project / 'openwrite.py'), 'setup']
        first = subprocess.run(command, cwd=self.project, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn('已创建本地配置', first.stdout)
        (self.project / '.env').write_text('WeChatAppID=custom\n', encoding='utf-8')
        second = subprocess.run(command, cwd=self.project, capture_output=True, text=True)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn('未覆盖', second.stdout)
        self.assertEqual((self.project / '.env').read_text(encoding='utf-8'), 'WeChatAppID=custom\n')

    def test_template_never_participates_in_runtime_resolution(self):
        (self.project / '.env.example').write_text(
            'WeChat=false\nRednote=true\nSelfMediaBlogger=false\nProductManager=true\n'
            f'WeChatAppID={APPID}\nWeChatAppSecret=from-template\n', encoding='utf-8')
        # 只有模板时没有可用配置，必须向用户确认，而不是套用模板值。
        with self.assertRaises(preferences.ChoiceRequired):
            preferences.resolve(self.project)
        with self.assertRaises(ValueError):
            preferences.require_wechat_credentials(self.project)
        (self.project / '.env').write_text('WeChat=true\nSelfMediaBlogger=true\n', encoding='utf-8')
        selection = preferences.resolve(self.project)
        self.assertEqual((selection['platform'], selection['perspective']), ('wechat', 'blogger'))
        self.assertEqual(preferences.read_values(self.project).get('WeChatAppID'), None)

    def test_credentials_come_only_from_env_and_reject_placeholders(self):
        (self.project / '.env.example').write_text(
            TEMPLATE.replace('WeChatAppID=', f'WeChatAppID={APPID}')
                    .replace('WeChatAppSecret=', 'WeChatAppSecret=from-template'),
            encoding='utf-8')
        with self.assertRaises(ValueError):
            preferences.require_wechat_credentials(self.project)
        (self.project / '.env').write_text(
            f'WeChatAppID={APPID}\nWeChatAppSecret=from-env\nWeChatAuthor="我的 公众号"\n',
            encoding='utf-8')
        credentials = preferences.require_wechat_credentials(self.project)
        self.assertEqual((credentials['appid'], credentials['appsecret']), (APPID, 'from-env'))
        self.assertEqual(credentials['author'], '我的 公众号')
        (self.project / '.env').write_text('WeChatAppID=your_appid_here\nWeChatAppSecret=changeme\n',
                                           encoding='utf-8')
        with self.assertRaises(ValueError) as error:
            preferences.require_wechat_credentials(self.project)
        self.assertIn('openwrite.py setup', str(error.exception))

    def test_writing_a_value_requires_existing_env(self):
        with self.assertRaises(ValueError) as error:
            preferences.set_env_value(self.project, 'WeChatAuthor', '作者')
        self.assertIn('openwrite.py setup', str(error.exception))
        self.assertFalse((self.project / '.env').exists())

    def test_missing_credentials_point_to_local_env_not_home_config(self):
        with self.assertRaises(ValueError) as error:
            preferences.require_wechat_credentials(self.project)
        message = str(error.exception)
        self.assertIn(str(self.project / '.env'), message)
        self.assertIn('WeChatAppID', message)
        self.assertNotIn('.wechat-publisher', message)

    def test_author_write_back_preserves_other_lines_and_comments(self):
        preferences.init_env(self.project)
        (self.project / '.env').write_text(
            '# 注释\nWeChat=true\nWeChatAppID=' + APPID + '\nWeChatAppSecret=secret\n',
            encoding='utf-8')
        preferences.set_env_value(self.project, 'WeChatAuthor', '作者 甲')
        text = (self.project / '.env').read_text(encoding='utf-8')
        self.assertIn('# 注释', text)
        self.assertIn(f'WeChatAppID={APPID}', text)
        self.assertIn('WeChatAppSecret=secret', text)
        self.assertIn('WeChatAuthor="作者 甲"', text)
        self.assertEqual((self.project / '.env').stat().st_mode & 0o777, 0o600)
        self.assertEqual(preferences.wechat_credentials(self.project)['author'], '作者 甲')
        preferences.set_env_value(self.project, 'WeChatAuthor', '作者乙')
        text = (self.project / '.env').read_text(encoding='utf-8')
        self.assertEqual(text.count('WeChatAuthor'), 1)
        self.assertEqual(preferences.wechat_credentials(self.project)['author'], '作者乙')
        with self.assertRaises(ValueError):
            preferences.set_env_value(self.project, 'UnknownKey', 'x')

    def test_project_gitignore_keeps_env_local_and_template_tracked(self):
        if shutil.which('git') is None or not (ROOT / '.git').exists():
            self.skipTest('需要 Git 仓库')
        for name, ignored in (('.env', True), ('.env.example', False)):
            result = subprocess.run(['git', '-C', str(ROOT), 'check-ignore', '-q', name])
            self.assertEqual(result.returncode == 0, ignored, name)


class PublisherConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-publisher-')
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name).resolve()
        (self.project / '.env.example').write_text(TEMPLATE, encoding='utf-8')
        self.publisher = load_publisher()
        self.home = self.project / 'home'
        self.home.mkdir()
        patcher = patch.dict(os.environ, {'HOME': str(self.home)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def configure(self):
        preferences.init_env(self.project)
        preferences.set_env_value(self.project, 'WeChatAppID', APPID)
        preferences.set_env_value(self.project, 'WeChatAppSecret', 'secret-value')

    def test_publisher_reads_project_env_and_never_creates_home_config(self):
        self.configure()
        with redirect_stdout(io.StringIO()):
            instance = self.publisher.WeChatPublisher(self.project)
        self.assertEqual((instance.appid, instance.appsecret), (APPID, 'secret-value'))
        self.assertFalse((self.home / '.wechat-publisher').exists())

    def test_missing_credentials_fail_before_any_api_call(self):
        with patch.object(self.publisher.requests, 'get') as request:
            with redirect_stdout(io.StringIO()):
                with self.assertRaises(ValueError) as error:
                    self.publisher.WeChatPublisher(self.project)
            request.assert_not_called()
        self.assertIn('openwrite.py setup', str(error.exception))
        self.assertFalse((self.home / '.wechat-publisher').exists())

    def test_author_is_saved_into_project_env(self):
        self.configure()
        with redirect_stdout(io.StringIO()):
            instance = self.publisher.WeChatPublisher(self.project)
            instance.save_author('测试作者')
            self.assertEqual(self.publisher.WeChatPublisher(self.project).author, '测试作者')
        self.assertEqual(preferences.wechat_credentials(self.project)['author'], '测试作者')
        self.assertFalse((self.home / '.wechat-publisher').exists())

    def test_invalid_env_syntax_is_reported_without_network(self):
        (self.project / '.env').write_text('WeChatAppID="unterminated\n', encoding='utf-8')
        with patch.object(self.publisher.requests, 'get') as request:
            with self.assertRaises(ValueError):
                self.publisher.WeChatPublisher(self.project)
            request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
