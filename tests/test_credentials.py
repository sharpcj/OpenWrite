"""Local openwrite.yaml setup, multi-account isolation and WeChat credential loading.

No network or home-directory config is touched.
"""
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
TEMPLATE = ('defaults:\n  writer_role: blogger\n'
            'wechat:\n  accounts:\n    主号:\n      app_id: ""\n      app_secret: ""\n      author: ""\n')
APPID = 'wx1234567890abcdef'


def write_config(project, text):
    (project / preferences.CONFIG_NAME).write_text(text, encoding='utf-8')


def account_yaml(appid=APPID, secret='secret-value', author='', name='主号', extra=''):
    return (f'wechat:\n  accounts:\n    {name}:\n'
            f'      app_id: "{appid}"\n      app_secret: "{secret}"\n'
            f'      author: "{author}"\n{extra}')


def load_publisher():
    path = ROOT / 'skills/wechat-draft-publisher/publisher.py'
    spec = importlib.util.spec_from_file_location('publisher_credentials_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ConfigSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-credentials-')
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name).resolve()
        (self.project / preferences.TEMPLATE_NAME).write_text(TEMPLATE, encoding='utf-8')

    def test_setup_copies_template_once_with_owner_only_permissions(self):
        target, created = preferences.init_config(self.project)
        self.assertTrue(created)
        self.assertEqual(target, self.project / preferences.CONFIG_NAME)
        self.assertEqual(target.read_text(encoding='utf-8'), TEMPLATE)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        target.write_text('defaults:\n  writer_role: tech\n', encoding='utf-8')
        again, created = preferences.init_config(self.project)
        self.assertFalse(created)
        self.assertEqual(again.read_text(encoding='utf-8'), 'defaults:\n  writer_role: tech\n')

    def test_setup_requires_template_and_refuses_symlink(self):
        (self.project / preferences.TEMPLATE_NAME).unlink()
        with self.assertRaises(ValueError):
            preferences.init_config(self.project)
        (self.project / preferences.TEMPLATE_NAME).write_text(TEMPLATE, encoding='utf-8')
        outside = self.project / 'outside'
        outside.write_text('secret', encoding='utf-8')
        (self.project / preferences.CONFIG_NAME).symlink_to(outside)
        with self.assertRaises(ValueError):
            preferences.init_config(self.project)
        self.assertEqual(outside.read_text(encoding='utf-8'), 'secret')

    def test_cli_setup_creates_config_and_second_run_keeps_it(self):
        for name in ('openwrite.py', 'workflow.py', 'preferences.py', 'platforms.py', 'layout.py',
                     'writer_roles.py'):
            shutil.copy2(ROOT / name, self.project / name)
        shutil.copytree(ROOT / 'writer_roles', self.project / 'writer_roles', dirs_exist_ok=True)
        shutil.copy2(ROOT / preferences.TEMPLATE_NAME, self.project / preferences.TEMPLATE_NAME)
        command = [sys.executable, '-B', str(self.project / 'openwrite.py'), 'setup']
        first = subprocess.run(command, cwd=self.project, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn('已创建本地配置', first.stdout)
        write_config(self.project, 'defaults:\n  writer_role: tech\n')
        second = subprocess.run(command, cwd=self.project, capture_output=True, text=True)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn('未覆盖', second.stdout)
        self.assertEqual((self.project / preferences.CONFIG_NAME).read_text(encoding='utf-8'),
                         'defaults:\n  writer_role: tech\n')

    def test_template_never_participates_in_runtime_resolution(self):
        (self.project / preferences.TEMPLATE_NAME).write_text(
            'defaults:\n  writer_role: product\n' + account_yaml(secret='from-template'),
            encoding='utf-8')
        # 只有模板时没有可用配置，必须向用户确认，而不是套用模板值。
        with self.assertRaises(preferences.ChoiceRequired):
            preferences.resolve(self.project)
        with self.assertRaises(ValueError):
            preferences.require_wechat_credentials(self.project)
        write_config(self.project, 'wechat:\n  accounts:\n    主号: {}\n')
        selection = preferences.resolve(self.project)
        self.assertEqual((selection['platform'], selection['perspective']), ('wechat', 'blogger'))
        self.assertEqual(preferences.wechat_credentials(self.project)['appid'], '')

    def test_credentials_come_only_from_config_and_reject_placeholders(self):
        (self.project / preferences.TEMPLATE_NAME).write_text(
            account_yaml(secret='from-template'), encoding='utf-8')
        with self.assertRaises(ValueError):
            preferences.require_wechat_credentials(self.project)
        write_config(self.project, account_yaml(secret='from-config', author='我的 公众号'))
        credentials = preferences.require_wechat_credentials(self.project)
        self.assertEqual((credentials['appid'], credentials['appsecret']), (APPID, 'from-config'))
        self.assertEqual(credentials['author'], '我的 公众号')
        write_config(self.project, account_yaml(appid='your_appid_here', secret='changeme'))
        with self.assertRaises(ValueError) as error:
            preferences.require_wechat_credentials(self.project)
        self.assertIn('openwrite.py setup', str(error.exception))

    def test_missing_credentials_point_to_local_config_not_home_config(self):
        with self.assertRaises(ValueError) as error:
            preferences.require_wechat_credentials(self.project)
        message = str(error.exception)
        self.assertIn(str(self.project / preferences.CONFIG_NAME), message)
        self.assertIn('app_id', message)
        self.assertNotIn('.wechat-publisher', message)

    def test_author_write_back_preserves_other_lines_and_comments(self):
        write_config(self.project,
                     '# 顶部注释\nwechat:\n  accounts:\n    主号:\n'
                     f'      app_id: "{APPID}"\n      app_secret: "secret"\n      # 账号注释\n')
        preferences.set_account_author(self.project, '主号', '作者 甲')
        text = (self.project / preferences.CONFIG_NAME).read_text(encoding='utf-8')
        self.assertIn('# 顶部注释', text)
        self.assertIn('# 账号注释', text)
        self.assertIn(f'app_id: "{APPID}"', text)
        self.assertIn('app_secret: "secret"', text)
        self.assertIn('author: "作者 甲"', text)
        self.assertEqual((self.project / preferences.CONFIG_NAME).stat().st_mode & 0o777, 0o600)
        self.assertEqual(preferences.wechat_credentials(self.project)['author'], '作者 甲')
        preferences.set_account_author(self.project, '主号', '作者乙')
        text = (self.project / preferences.CONFIG_NAME).read_text(encoding='utf-8')
        self.assertEqual(text.count('author:'), 1)
        self.assertEqual(preferences.wechat_credentials(self.project)['author'], '作者乙')
        with self.assertRaises(ValueError):
            preferences.set_account_author(self.project, '不存在的号', 'x')

    def test_project_gitignore_keeps_config_local_and_template_tracked(self):
        if shutil.which('git') is None or not (ROOT / '.git').exists():
            self.skipTest('需要 Git 仓库')
        for name, ignored in ((preferences.CONFIG_NAME, True), (preferences.TEMPLATE_NAME, False)):
            result = subprocess.run(['git', '-C', str(ROOT), 'check-ignore', '-q', name])
            self.assertEqual(result.returncode == 0, ignored, name)


class AccountIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-accounts-')
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name).resolve()

    def test_multiple_accounts_require_choice_or_default(self):
        write_config(self.project,
                     'wechat:\n  accounts:\n    甲:\n      app_id: "wx1"\n      app_secret: "s1"\n'
                     '    乙:\n      app_id: "wx2"\n      app_secret: "s2"\n')
        with self.assertRaises(preferences.ChoiceRequired) as error:
            preferences.resolve(self.project)
        self.assertIn('--account', str(error.exception))
        selection = preferences.resolve(self.project, account='乙')
        self.assertEqual((selection['platform'], selection['account']), ('wechat', '乙'))
        self.assertEqual(selection['selection_source']['account'], 'explicit')

    def test_default_account_is_used_when_present(self):
        write_config(self.project,
                     'wechat:\n  default_account: 乙\n  accounts:\n'
                     '    甲:\n      app_id: "wx1"\n      app_secret: "s1"\n'
                     '    乙:\n      app_id: "wx2"\n      app_secret: "s2"\n')
        selection = preferences.resolve(self.project)
        self.assertEqual(selection['account'], '乙')
        self.assertEqual(selection['selection_source']['account'], 'config')
        self.assertEqual(preferences.wechat_credentials(self.project)['appid'], 'wx2')

    def test_credentials_are_isolated_per_account(self):
        write_config(self.project,
                     'wechat:\n  accounts:\n    甲:\n      app_id: "wx1"\n      app_secret: "s1"\n'
                     '      author: "作者甲"\n    乙:\n      app_id: "wx2"\n      app_secret: "s2"\n')
        self.assertEqual(preferences.wechat_credentials(self.project, '甲')['author'], '作者甲')
        self.assertEqual(preferences.wechat_credentials(self.project, '乙')['appid'], 'wx2')
        self.assertEqual(preferences.wechat_credentials(self.project, '乙')['author'], '')
        with self.assertRaises(ValueError):
            preferences.wechat_credentials(self.project, '丙')

    def test_account_can_imply_platform_and_cover_is_per_account(self):
        write_config(self.project,
                     'wechat:\n  accounts:\n    甲:\n      cover:\n        layout: 居中标题\n'
                     'rednote:\n  accounts:\n    小红书号:\n      cookie: "a1=x; web_session=y"\n')
        selection = preferences.resolve(self.project, account='小红书号')
        self.assertEqual(selection['platform'], 'rednote')
        self.assertEqual(preferences.cover_style(self.project, account='甲'), {'layout': '居中标题'})
        self.assertEqual(preferences.xhs_cookie(self.project, '小红书号'), 'a1=x; web_session=y')

    def test_account_override_of_role_and_checkpoint(self):
        write_config(self.project,
                     'defaults:\n  writer_role: blogger\n  outline_approval: true\n'
                     'wechat:\n  accounts:\n    甲:\n      writer_role: tech\n      outline_approval: false\n'
                     '    乙: {}\n')
        self.assertEqual(preferences.resolve(self.project, account='甲')['perspective'], 'tech')
        self.assertFalse(preferences.outline_approval(self.project, 'wechat', '甲'))
        self.assertEqual(preferences.resolve(self.project, account='乙')['perspective'], 'blogger')
        self.assertTrue(preferences.outline_approval(self.project, 'wechat', '乙'))

    def test_disabled_platform_is_not_enabled(self):
        write_config(self.project,
                     'wechat:\n  enabled: false\n  accounts:\n    甲: {}\n'
                     'rednote:\n  accounts:\n    号:\n      cookie: "a1=x; web_session=y"\n')
        self.assertEqual(preferences.enabled_platforms(self.project), ['rednote'])
        self.assertEqual(preferences.resolve(self.project)['platform'], 'rednote')

    def test_account_name_label_is_accepted(self):
        write_config(self.project,
                     'wechat:\n  accounts:\n    账号1:\n      name: "星河观察"\n'
                     '      app_id: "wx1"\n      app_secret: "s1"\n'
                     'rednote:\n  accounts:\n    账号1:\n      name: "星河的小红书"\n'
                     '      cookie: "a1=x; web_session=y"\n')
        config = preferences.read_config(self.project)
        self.assertEqual(config['wechat']['accounts']['账号1']['name'], '星河观察')
        self.assertEqual(config['rednote']['accounts']['账号1']['name'], '星河的小红书')
        self.assertEqual(preferences.resolve(self.project, platform='wechat')['account'], '账号1')

    def test_unknown_fields_and_bad_types_are_rejected(self):
        for text in ('wechat:\n  accounts:\n    甲:\n      bogus: 1\n',
                     'defaults:\n  outline_approval: maybe\n',
                     'defaults:\n  writer_role: engineer\n',
                     'unknown_section: {}\n',
                     'wechat:\n  default_account: 不存在\n  accounts:\n    甲: {}\n'):
            with self.subTest(text=text):
                write_config(self.project, text)
                with self.assertRaises(ValueError):
                    preferences.read_config(self.project)


class PublisherConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-publisher-')
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name).resolve()
        (self.project / preferences.TEMPLATE_NAME).write_text(TEMPLATE, encoding='utf-8')
        self.publisher = load_publisher()
        self.home = self.project / 'home'
        self.home.mkdir()
        patcher = patch.dict(os.environ, {'HOME': str(self.home)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def configure(self):
        write_config(self.project, account_yaml())

    def test_publisher_reads_project_config_and_never_creates_home_config(self):
        self.configure()
        with redirect_stdout(io.StringIO()):
            instance = self.publisher.WeChatPublisher(self.project)
        self.assertEqual((instance.appid, instance.appsecret), (APPID, 'secret-value'))
        self.assertEqual(instance.account, '主号')
        self.assertFalse((self.home / '.wechat-publisher').exists())

    def test_token_cache_is_isolated_per_appid(self):
        write_config(self.project,
                     'wechat:\n  accounts:\n    甲:\n      app_id: "wx1111111111111111"\n'
                     '      app_secret: "s1"\n    乙:\n      app_id: "wx2222222222222222"\n'
                     '      app_secret: "s2"\n')
        with redirect_stdout(io.StringIO()):
            first = self.publisher.WeChatPublisher(self.project, account='甲')
            second = self.publisher.WeChatPublisher(self.project, account='乙')
        self.assertNotEqual(first.token_cache_file, second.token_cache_file)
        self.assertIn('wx1111111111111111', first.token_cache_file)
        self.assertIn('wx2222222222222222', second.token_cache_file)

    def test_missing_credentials_fail_before_any_api_call(self):
        with patch.object(self.publisher.requests, 'get') as request:
            with redirect_stdout(io.StringIO()):
                with self.assertRaises(ValueError) as error:
                    self.publisher.WeChatPublisher(self.project)
            request.assert_not_called()
        self.assertIn('openwrite.py setup', str(error.exception))
        self.assertFalse((self.home / '.wechat-publisher').exists())

    def test_author_is_saved_into_project_config(self):
        self.configure()
        with redirect_stdout(io.StringIO()):
            instance = self.publisher.WeChatPublisher(self.project)
            instance.save_author('测试作者')
            self.assertEqual(self.publisher.WeChatPublisher(self.project).author, '测试作者')
        self.assertEqual(preferences.wechat_credentials(self.project)['author'], '测试作者')
        self.assertFalse((self.home / '.wechat-publisher').exists())

    def test_invalid_yaml_is_reported_without_network(self):
        write_config(self.project, 'wechat:\n  accounts:\n    甲:\n      app_id: "unterminated\n')
        with patch.object(self.publisher.requests, 'get') as request:
            with self.assertRaises(ValueError):
                self.publisher.WeChatPublisher(self.project)
            request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
