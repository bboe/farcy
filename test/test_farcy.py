"""Farcy class test file."""

from __future__ import print_function
from collections import namedtuple
from farcy import Farcy, FarcyException
from github3 import GitHub, GitHubError
from io import IOBase
from mock import MagicMock, patch
import unittest


MockInfo = namedtuple('Info', ['decoded'])
MockPFile = namedtuple('PFile', ['contents', 'filename'])
MockResponse = namedtuple('MockResponse', ['content', 'status_code'])


class FarcyTest(unittest.TestCase):

    @patch('farcy.Farcy.get_session')
    @patch('farcy.UpdateChecker')
    def _farcy_instance(self, mock_get_session, mock_update_checker):
        farcy = Farcy('dummy', 'dummy')
        self.assertTrue(mock_get_session.called)
        self.assertTrue(mock_update_checker.called)
        return farcy

    def test_get_issues__simple_module(self):
        farcy = self._farcy_instance()
        pfile = MockPFile(contents=lambda: MockInfo(decoded=b'"""A."""\n'),
                          filename='a.py')
        self.assertEqual({}, farcy.get_issues(pfile))

    def test_get_issues__no_handlers(self):
        farcy = self._farcy_instance()
        pfile = MockPFile(contents=None, filename='')
        self.assertEqual({}, farcy.get_issues(pfile))

    @patch('farcy.open', create=True)
    @patch('github3.authorize')
    @patch('getpass.getpass')
    @patch('farcy.Farcy.prompt')
    @patch('farcy.os.path')
    def test_get_session__authenticate(self, mock_path, mock_prompt,
                                       mock_getpass, mock_authorize,
                                       mock_open):
        mock_path.isfile.return_value = False
        self.assertTrue(isinstance(Farcy.get_session(), GitHub))
        self.assertTrue(mock_prompt.called)
        self.assertTrue(mock_getpass.called)
        self.assertTrue(mock_open.called)

    @patch('github3.authorize')
    @patch('getpass.getpass')
    @patch('farcy.Farcy.prompt')
    @patch('farcy.os.path')
    def test_get_session__authenticate_with_exceptions(
            self, mock_path, mock_prompt, mock_getpass, mock_authorize):
        mock_path.isfile.return_value = False

        mock_response = MockResponse(content='', status_code=401)
        mock_authorize.side_effect = GitHubError(mock_response)
        self.assertRaises(FarcyException, Farcy.get_session)

        self.assertTrue(mock_prompt.called)
        self.assertTrue(mock_getpass.called)

        mock_response = MockResponse(content='', status_code=101)
        mock_authorize.side_effect = GitHubError(mock_response)
        self.assertRaises(GitHubError, Farcy.get_session)

        mock_authorize.side_effect = TypeError
        self.assertRaises(TypeError, Farcy.get_session)

    @patch.object(GitHub, 'is_starred')
    @patch('farcy.open', create=True)
    @patch('farcy.os.path')
    def test_get_session__from_credentials_file(self, mock_path, mock_open,
                                                mock_is_starred):
        mock_path.expanduser.return_value = 'mock_path'
        mock_path.isfile.return_value = True
        mock_open.return_value = MagicMock(spec=IOBase)
        self.assertTrue(Farcy.get_session())
        self.assertTrue(mock_is_starred.called)

    @patch('github3.authorize')
    @patch('getpass.getpass')
    @patch('farcy.Farcy.prompt')
    @patch('farcy.sys.stderr')
    @patch.object(GitHub, 'is_starred')
    @patch('farcy.open', create=True)
    @patch('farcy.os.path')
    def test_get_session__from_credentials_file__handled_exception(
            self, mock_path, mock_open, mock_is_starred, mock_stderr,
            mock_prompt, mock_getpass, mock_authorize):
        mock_path.expanduser.return_value = 'mock_path'
        mock_path.isfile.return_value = True
        mock_open.return_value = MagicMock(spec=IOBase)

        mock_response = MockResponse(content='', status_code=401)
        mock_is_starred.side_effect = GitHubError(mock_response)
        self.assertTrue(isinstance(Farcy.get_session(), GitHub))
        self.assertTrue(mock_stderr.write.called)
        self.assertTrue(mock_prompt.called)
        self.assertTrue(mock_getpass.called)
        self.assertTrue(mock_open.called)

    @patch.object(GitHub, 'is_starred')
    @patch('farcy.open', create=True)
    @patch('farcy.os.path')
    def test_get_session__from_credentials_file__unhandled_exception(
            self, mock_path, mock_open, mock_is_starred):
        mock_path.expanduser.return_value = 'mock_path'
        mock_path.isfile.return_value = True
        mock_open.return_value = MagicMock(spec=IOBase)

        mock_is_starred.side_effect = TypeError
        self.assertRaises(TypeError, Farcy.get_session)

    @patch('farcy.sys.stdin')
    @patch('farcy.sys.stdout')
    def test_prompt(self, mock_stdout, mock_stdin):
        mock_stdin.readline.return_value = ' hello '
        self.assertEqual('hello', Farcy.prompt('my message'))
        mock_stdout.write.assert_called_with('my message: ')
        self.assertTrue(mock_stdout.flush.called)
