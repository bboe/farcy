"""Farcy class test file."""

from __future__ import print_function
from collections import namedtuple
from farcy import Farcy, FarcyException, no_handler_debug_factory
from farcy.helpers import Config
from github3 import GitHub, GitHubError
from io import IOBase
from mock import MagicMock, call, patch
import logging
import unittest

PFILE_ATTRS = ['contents', 'filename', 'patch', 'status']

MockInfo = namedtuple('Info', ['decoded'])
MockPFile = namedtuple('PFile', PFILE_ATTRS)
MockResponse = namedtuple('MockResponse', ['content', 'status_code'])


def mockpfile(**kwargs):
    for attr in PFILE_ATTRS:
        kwargs.setdefault(attr, None)
    return MockPFile(**kwargs)


class FarcyTest(unittest.TestCase):

    @patch('farcy.Farcy.get_session')
    @patch('farcy.UpdateChecker')
    def _farcy_instance(self, mock_get_session, mock_update_checker,
                        config=Config()):
        if config.repository is None:
            config.repository = 'dummy/dummy'
        farcy = Farcy(config)
        self.assertTrue(mock_get_session.called)
        self.assertTrue(mock_update_checker.called)
        return farcy

    @patch('farcy.added_lines')
    def test_compute_pfile_stats__added(self, mock_added_lines):
        mock_added_lines.return_value = {13: 10, 15: 20, 18: 100}
        stats = {'added_files': 10, 'added_lines': 10}
        actual = self._farcy_instance()._compute_pfile_stats(
            mockpfile(patch='', status='added'), stats)
        self.assertTrue(mock_added_lines.called)
        self.assertEqual(mock_added_lines.return_value, actual)
        self.assertEqual({'added_files': 11, 'added_lines': 13}, stats)

    def test_compute_pfile_stats__excluded(self):
        stats = {'blacklisted_files': 10}
        config = Config()
        config.exclude_paths = ['tmp/*']
        farcy = self._farcy_instance(config=config)
        self.assertEqual(None, farcy._compute_pfile_stats(
            mockpfile(filename='tmp/foo'), stats))
        self.assertEqual({'blacklisted_files': 11}, stats)

    @patch('farcy.added_lines')
    def test_compute_pfile_stats__modified(self, mock_added_lines):
        mock_added_lines.return_value = {1: 1, 2: 2}
        for status in ['modified', 'renamed']:
            stats = {'modified_files': 10, 'modified_lines': 10}
            actual = self._farcy_instance()._compute_pfile_stats(
                mockpfile(patch='', status=status), stats)
            self.assertTrue(mock_added_lines.called)
            mock_added_lines.reset_mock()
            self.assertEqual(mock_added_lines.return_value, actual)
            self.assertEqual({'modified_files': 11, 'modified_lines': 12},
                             stats)

    def test_compute_pfile_stats__no_change(self):
        stats = {'unchanged_files': 10}
        self.assertEqual(None, self._farcy_instance()._compute_pfile_stats(
            mockpfile(status='added'), stats))
        self.assertEqual({'unchanged_files': 11}, stats)

    def test_compute_pfile_stats__removed(self):
        stats = {'deleted_files': 10}
        config = Config()
        config.exclude_paths = ['tmp/*']
        farcy = self._farcy_instance(config=config)
        self.assertEqual(None, farcy._compute_pfile_stats(
            mockpfile(filename='a/tmp/b', status='removed'), stats))
        self.assertEqual({'deleted_files': 11}, stats)

    def test_compute_pfile_stats__unexpected_status(self):
        logger = logging.getLogger('farcy')
        stats = {}
        with patch.object(logger, 'critical') as mock_critical:
            self.assertEqual(None, self._farcy_instance()._compute_pfile_stats(
                mockpfile(patch='', status='foobar'), stats))
            self.assertTrue(mock_critical.called)
        self.assertEqual({}, stats)

    def test_get_issues__simple_module(self):
        farcy = self._farcy_instance()
        pfile = mockpfile(contents=lambda: MockInfo(decoded=b'"""A."""\n'),
                          filename='a.py')
        self.assertEqual({}, farcy.get_issues(pfile))

    def test_get_issues__no_handlers(self):
        farcy = self._farcy_instance()
        self.assertEqual({}, farcy.get_issues(mockpfile(filename='')))

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


class NoHandlerDebugFactory(unittest.TestCase):
    def setUp(self):
        self.farcy = MagicMock()

    def test_no_handler_factory__cache_response(self):
        func = no_handler_debug_factory(1)
        func(self.farcy, '.js')
        func(self.farcy, '.js')
        self.farcy.log.debug.assert_called_once_with(
            'No handlers for extension .js')

    def test_no_handler_factory__output_when_cache_expired(self):
        func = no_handler_debug_factory(0)
        func(self.farcy, '.js')
        func(self.farcy, '.js')
        calls = [call('No handlers for extension .js')] * 2
        self.farcy.log.debug.assert_has_calls(calls)

    def test_no_handler_factory__multiple_calls(self):
        func = no_handler_debug_factory(1)
        func(self.farcy, '.js')
        func(self.farcy, '.css')
        calls = [call('No handlers for extension .js'),
                 call('No handlers for extension .css')]
        self.farcy.log.debug.assert_has_calls(calls)
