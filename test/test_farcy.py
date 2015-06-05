"""Farcy class test file."""

from __future__ import print_function
from farcy import Farcy
from github3 import GitHub
from io import IOBase
from mock import MagicMock, patch
import unittest


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
