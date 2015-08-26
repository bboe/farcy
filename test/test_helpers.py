"""Farcy test file."""

from __future__ import print_function
from collections import namedtuple
from farcy import helpers
from github3 import GitHub, GitHubError
from io import IOBase
from mock import MagicMock, patch
import unittest
import farcy.exceptions as exceptions


MockResponse = namedtuple('MockResponse', ['content', 'status_code'])


class MockComment(object):
    """Imitates a review comment."""

    def __init__(self, body=None, path=None, position=None, issues=None):
        if issues:
            body = '\n'.join([helpers.FARCY_COMMENT_START] +
                             ['* ' + issue for issue in issues])
        self.body = body
        self.path = path
        self.position = position


class ConfigTest(unittest.TestCase):
    """Tests Config helper."""

    @patch('farcy.helpers.ConfigParser')
    @patch('os.path.isfile')
    def _config_instance(self, callback, mock_is_file, mock_config, repo=None,
                         post_callback=None):
        mock_is_file.called_with(helpers.Config.PATH).return_value = True

        if callback:
            callback(mock_config.return_value)
        config = helpers.Config(repo)
        if post_callback:
            post_callback(mock_config.return_value)
        self.assertTrue(mock_config.called)
        return config

    def test_cant_change_log_level_if_debug(self):
        config = self._config_instance(None, repo='a/b')
        self.assertNotEqual('DEBUG', config.log_level)
        config.debug = True
        self.assertEqual('DEBUG', config.log_level)
        config.log_level = 'WARNING'
        self.assertEqual('DEBUG', config.log_level)

    def test_config_file_is_overridable(self):
        def callback(mock_config):
            mock_config.items.return_value = {'start_event': '1337'}
        config = self._config_instance(callback, repo='a/b')
        self.assertEqual(1337, config.start_event)
        config.start_event = 10
        self.assertEqual(10, config.start_event)

    def test_config_file_repo_specific_works(self):
        def callback(mock_config):
            mock_config.has_section.return_value = True
            mock_config.items.return_value = {'start_event': '1337'}

        def post_callback(mock_config):
            mock_config.items.assert_called_with('a/b')
        config = self._config_instance(callback, repo='a/b',
                                       post_callback=post_callback)
        self.assertEqual('a/b', config.repository)
        self.assertEqual(1337, config.start_event)

    def test_config_file_values(self):
        def callback(mock_config):
            mock_config.has_section.return_value = False
            mock_config.items.return_value = {
                'start_event': '10', 'debug': True,
                'exclude_paths': 'node_modules,vendor',
                'limit_users': 'balloob,bboe', 'log_level': 'DEBUG',
                'pr_issue_report_limit': '100'}

        def post_callback(mock_config):
            mock_config.items.assert_called_with('DEFAULT')
        config = self._config_instance(callback, repo='a/b',
                                       post_callback=post_callback)
        self.assertEqual('a/b', config.repository)
        self.assertEqual(10, config.start_event)
        self.assertEqual(True, config.debug)
        self.assertEqual({'node_modules', 'vendor'}, config.exclude_paths)
        self.assertEqual({'balloob', 'bboe'}, config.limit_users)
        self.assertEqual('DEBUG', config.log_level)
        self.assertEqual(100, config.pr_issue_report_limit)

    def test_default_repo_from_config(self):
        def callback(mock_config):
            mock_config.get.return_value = 'appfolio/farcy'
        config = self._config_instance(callback)
        self.assertEqual('appfolio/farcy', config.repository)

    def test_default_repo_from_config_raise_on_invalid(self):
        def callback(mock_config):
            mock_config.get.return_value = 'invalid_repo'
        with self.assertRaises(exceptions.FarcyException):
            self._config_instance(callback)

    def test_raise_if_invalid_log_level(self):
        config = self._config_instance(None, repo='a/b')
        with self.assertRaises(exceptions.FarcyException):
            config.log_level = 'invalid_log_level'

    def test_raise_if_invalid_repository(self):
        config = self._config_instance(None, repo='a/b')
        with self.assertRaises(exceptions.FarcyException):
            config.repository = 'invalid_repo'

    def test_setting_repo(self):
        config = self._config_instance(None, repo='a/b')
        self.assertEqual('a/b', config.repository)
        config.repository = 'appfolio/farcy'
        self.assertEqual('appfolio/farcy', config.repository)

    def test_setting_values_via_dict(self):
        config = self._config_instance(None, repo='appfolio/farcy')
        data = {
            'start_event': 1000,
            'debug': False,
            'exclude_paths': {'npm_modules', 'vendor'},
            'limit_users': {'balloob', 'bboe'},
            'log_level': 'WARNING',
            'pr_issue_report_limit': 100
        }

        config.override(**data)
        for attr, value in data.items():
            self.assertEqual(value, getattr(config, attr))

    def test_user_whitelisted_passes_if_not_set(self):
        config = self._config_instance(None, repo='a/b')
        self.assertTrue(config.user_whitelisted('balloob'))

    def test_user_whitelisted_works_if_set(self):
        config = self._config_instance(None, repo='a/b')
        config.limit_users = ['bboe', 'balloob']
        self.assertTrue(config.user_whitelisted('balloob'))
        self.assertFalse(config.user_whitelisted('appfolio'))


class CommentFunctionTest(unittest.TestCase):

    """Tests common Farcy handler extension methods."""
    def test_is_farcy_comment_detects_farcy_comment(self):
        self.assertTrue(helpers.is_farcy_comment(MockComment(
            issues=['Hello issue']).body))

    def test_is_farcy_comment_detects_if_not_farcy_comment(self):
        self.assertFalse(helpers.is_farcy_comment(MockComment(
            'Just a casual remark by not Farcy').body))

    def test_filter_comments_from_farcy(self):
        farcy_comment = MockComment(issues=['A issue'])
        normal_comment = MockComment('Casual remark')

        self.assertEqual(
            [farcy_comment],
            list(helpers.filter_comments_from_farcy(
                [normal_comment, farcy_comment])))

    def test_filter_comments_by_path(self):
        comment = MockComment('Casual remark', path='this/path')
        comment2 = MockComment('Why not like this', path='that/path')

        self.assertEqual(
            [comment2],
            list(helpers.filter_comments_by_path(
                [comment, comment2], 'that/path')))

    def test_extract_issues(self):
        issues = ['Hello', 'World']
        comment = MockComment(issues=issues)

        self.assertEqual(issues, helpers.extract_issues(comment.body))

    def test_issues_by_line_filters_non_farcy_comments(self):
        issues = ['Hello', 'World']
        issues2 = ['More', 'Issues']
        comment = MockComment(issues=issues, path='test.py', position=1)
        comment2 = MockComment(issues=issues2, path='test.py', position=1)
        comment3 = MockComment('hello world', path='test.py', position=1)

        self.assertEqual(
            {1: issues+issues2},
            helpers.issues_by_line([comment, comment2, comment3], 'test.py'))

    def test_subtract_issues_by_line(self):
        issues = {
            1: ['Hello', 'World'],
            5: ['Line 5', 'Issue'],
            6: ['All', 'Existing']
        }
        existing = {
            1: ['World'],
            2: ['Another existing'],
            5: ['Line 5', 'Beer'],
            6: ['All', 'Existing'],
        }

        self.assertEqual(
            {1: ['Hello'], 5: ['Issue']},
            helpers.subtract_issues_by_line(issues, existing))


class GetSessionTest(unittest.TestCase):
    @patch('farcy.helpers.open', create=True)
    @patch('github3.authorize')
    @patch('getpass.getpass')
    @patch('farcy.helpers.prompt')
    @patch('farcy.helpers.os.path')
    def test_get_session__authenticate(self, mock_path, mock_prompt,
                                       mock_getpass, mock_authorize,
                                       mock_open):
        mock_path.isfile.return_value = False
        self.assertTrue(isinstance(helpers.get_session(), GitHub))
        self.assertTrue(mock_prompt.called)
        self.assertTrue(mock_getpass.called)
        self.assertTrue(mock_open.called)

    @patch('github3.authorize')
    @patch('getpass.getpass')
    @patch('farcy.helpers.prompt')
    @patch('farcy.helpers.os.path')
    def test_get_session__authenticate_with_exceptions(
            self, mock_path, mock_prompt, mock_getpass, mock_authorize):
        mock_path.isfile.return_value = False

        mock_response = MockResponse(content='', status_code=401)
        mock_authorize.side_effect = GitHubError(mock_response)
        self.assertRaises(exceptions.FarcyException, helpers.get_session)

        self.assertTrue(mock_prompt.called)
        self.assertTrue(mock_getpass.called)

        mock_response = MockResponse(content='', status_code=101)
        mock_authorize.side_effect = GitHubError(mock_response)
        self.assertRaises(GitHubError, helpers.get_session)

        mock_authorize.side_effect = TypeError
        self.assertRaises(TypeError, helpers.get_session)

    @patch.object(GitHub, 'is_starred')
    @patch('farcy.helpers.open', create=True)
    @patch('farcy.helpers.os.path')
    def test_get_session__from_credentials_file(self, mock_path, mock_open,
                                                mock_is_starred):
        mock_path.expanduser.return_value = 'mock_path'
        mock_path.isfile.return_value = True
        mock_open.return_value = MagicMock(spec=IOBase)
        self.assertTrue(helpers.get_session())
        self.assertTrue(mock_is_starred.called)

    @patch('github3.authorize')
    @patch('getpass.getpass')
    @patch('farcy.helpers.prompt')
    @patch('farcy.helpers.sys.stderr')
    @patch.object(GitHub, 'is_starred')
    @patch('farcy.helpers.open', create=True)
    @patch('farcy.helpers.os.path')
    def test_get_session__from_credentials_file__handled_exception(
            self, mock_path, mock_open, mock_is_starred, mock_stderr,
            mock_prompt, mock_getpass, mock_authorize):
        mock_path.expanduser.return_value = 'mock_path'
        mock_path.isfile.return_value = True
        mock_open.return_value = MagicMock(spec=IOBase)

        mock_response = MockResponse(content='', status_code=401)
        mock_is_starred.side_effect = GitHubError(mock_response)
        self.assertTrue(isinstance(helpers.get_session(), GitHub))
        self.assertTrue(mock_stderr.write.called)
        self.assertTrue(mock_prompt.called)
        self.assertTrue(mock_getpass.called)
        self.assertTrue(mock_open.called)

    @patch.object(GitHub, 'is_starred')
    @patch('farcy.helpers.open', create=True)
    @patch('farcy.helpers.os.path')
    def test_get_session__from_credentials_file__unhandled_exception(
            self, mock_path, mock_open, mock_is_starred):
        mock_path.expanduser.return_value = 'mock_path'
        mock_path.isfile.return_value = True
        mock_open.return_value = MagicMock(spec=IOBase)

        mock_is_starred.side_effect = TypeError
        self.assertRaises(TypeError, helpers.get_session)


class PatchFunctionTest(unittest.TestCase):
    def test_added_lines(self):
        self.assertEqual({}, helpers.added_lines('@@+15'))
        self.assertEqual({1: 1}, helpers.added_lines('@@+1\n+wah'))
        self.assertEqual({15: 1}, helpers.added_lines('@@+15\n+wah'))
        self.assertEqual({16: 2}, helpers.added_lines('@@+15\n \n+wah'))
        self.assertEqual({1: 2}, helpers.added_lines('@@+1\n-\n+wah'))
        self.assertEqual({15: 2}, helpers.added_lines('@@+15\n-\n+wah'))
        self.assertEqual({16: 3}, helpers.added_lines('@@+15\n-\n \n+wah'))
        self.assertEqual({1: 1, 15: 3},
                         helpers.added_lines('@@+1\n+wah\n@@+15\n+foo'))

    def test_added_lines_works_with_github_no_newline_message(self):
        patch = """@@ -0,0 +1,5 @@
+class SomeClass
+  def yo(some_unused_param)
+    puts 'hi'
+  end
+end
\ No newline at end of file"""
        try:
            helpers.added_lines(patch)
        except AssertionError:
            self.fail('added_lines() raised AssertionError')


class PluralTest(unittest.TestCase):
    def test_plural__with_one__int(self):
        self.assertEqual('1 unit', helpers.plural(1, 'unit'))

    def test_plural__with_one__list(self):
        self.assertEqual('1 unit', helpers.plural([1], 'unit'))

    def test_plural__with_two__int(self):
        self.assertEqual('2 units', helpers.plural(2, 'unit'))

    def test_plural__with_two__list(self):
        self.assertEqual('2 units', helpers.plural([1, 2], 'unit'))

    def test_plural__with_zero__int(self):
        self.assertEqual('0 units', helpers.plural(0, 'unit'))

    def test_plural__with_zero__list(self):
        self.assertEqual('0 units', helpers.plural([], 'unit'))


class ParseSet(unittest.TestCase):
    def test_parse_set__comma_separated_as_string(self):
        self.assertEqual({'bar', 'bAz', 'foo'},
                         helpers.parse_set('foo, bar ,bAz'))

    def test_parse_set__comma_separated_in_list(self):
        self.assertEqual({'bar', 'baz', 'foo'},
                         helpers.parse_set(['foo, bar ,baz']))

    def test_parse_set__normalize(self):
        self.assertEqual({'hello'}, helpers.parse_set('HELLO', normalize=True))

    def test_parse_set__empty_input(self):
        self.assertEqual(None, helpers.parse_set([]))
        self.assertEqual(None, helpers.parse_set([',', '']))
        self.assertEqual(None, helpers.parse_set(''))
        self.assertEqual(None, helpers.parse_set(' '))

    def test_parse_set__separate_items(self):
        self.assertEqual(set(['bar', 'foo']),
                         helpers.parse_set(['foo', 'bar']))


class PromptTest(unittest.TestCase):
    @patch('farcy.helpers.sys.stdin')
    @patch('farcy.helpers.sys.stdout')
    def test_prompt(self, mock_stdout, mock_stdin):
        mock_stdin.readline.return_value = ' hello '
        self.assertEqual('hello', helpers.prompt('my message'))
        mock_stdout.write.assert_called_with('my message: ')
        self.assertTrue(mock_stdout.flush.called)


class SplitDictTest(unittest.TestCase):
    def test_split_dict(self):
        test_dict = {1: 'a', 2: 'b', 3: 'c'}

        with_keys, without_keys = helpers.split_dict(test_dict, [1, 2, 3])
        self.assertEqual(test_dict, with_keys)
        self.assertEqual({}, without_keys)

        with_keys, without_keys = helpers.split_dict(test_dict, [])
        self.assertEqual({}, with_keys)
        self.assertEqual(test_dict, without_keys)

        with_keys, without_keys = helpers.split_dict(test_dict, [2, 3])
        self.assertEqual({2: 'b', 3: 'c'}, with_keys)
        self.assertEqual({1: 'a'}, without_keys)
