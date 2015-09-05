"""Farcy helpers test file."""

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


class EnsureConfigDirTest(unittest.TestCase):
    @patch('os.makedirs')
    @patch('os.path.isdir')
    def test_ensure_config_dir__create(self, mock_isdir, mock_makedirs):
        mock_isdir.return_value = False
        helpers.ensure_config_dir()
        self.assertTrue(mock_isdir.called)
        mock_makedirs.assert_called_with(helpers.CONFIG_DIR, mode=0o700)

    @patch('os.makedirs')
    @patch('os.path.isdir')
    def test_ensure_config_dir__no_create(self, mock_isdir, mock_makedirs):
        mock_isdir.return_value = True
        helpers.ensure_config_dir()
        self.assertTrue(mock_isdir.called)
        self.assertFalse(mock_makedirs.called)


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


class ParseBool(unittest.TestCase):
    def test_parse_bool__non_string(self):
        for value in [True, -1, 1, 1000, [''], 1.0]:
            self.assertTrue(helpers.parse_bool(value))
        for value in [None, False, 0, '', [], {}, 0.0]:
            self.assertFalse(helpers.parse_bool(value))

    def test_parse_bool__string(self):
        for value in '1 on ON On oN t true y yes'.split():
            self.assertTrue(helpers.parse_bool(value))
        for value in '0 off OFF f false n no other'.split():
            self.assertFalse(helpers.parse_bool(value))


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
