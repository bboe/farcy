"""Farcy class test file."""

from __future__ import print_function
from collections import namedtuple
from farcy import Farcy, FarcyException
from github3 import GitHub, GitHubError
from io import IOBase
from mock import MagicMock, patch
import unittest


MockResponse = namedtuple('MockResponse', ['content', 'status_code'])


class FarcyTest(unittest.TestCase):
    def test_added_lines(self):
        self.assertEqual({}, Farcy.added_lines('@@+15'))
        self.assertEqual({1: 1}, Farcy.added_lines('@@+1\n+wah'))
        self.assertEqual({15: 1}, Farcy.added_lines('@@+15\n+wah'))
        self.assertEqual({16: 2}, Farcy.added_lines('@@+15\n \n+wah'))
        self.assertEqual({1: 2}, Farcy.added_lines('@@+1\n-\n+wah'))
        self.assertEqual({15: 2}, Farcy.added_lines('@@+15\n-\n+wah'))
        self.assertEqual({16: 3}, Farcy.added_lines('@@+15\n-\n \n+wah'))
        self.assertEqual({1: 1, 15: 3},
                         Farcy.added_lines('@@+1\n+wah\n@@+15\n+foo'))

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
    @patch.object(GitHub, 'is_starred')
    @patch('farcy.open', create=True)
    @patch('farcy.os.path')
    def test_get_session__from_credentials_file__handled_exception(
            self, mock_path, mock_open, mock_is_starred, mock_prompt,
            mock_getpass, mock_authorize):
        mock_path.expanduser.return_value = 'mock_path'
        mock_path.isfile.return_value = True
        mock_open.return_value = MagicMock(spec=IOBase)

        mock_response = MockResponse(content='', status_code=401)
        mock_is_starred.side_effect = GitHubError(mock_response)
        self.assertTrue(isinstance(Farcy.get_session(), GitHub))
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
